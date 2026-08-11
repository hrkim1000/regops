"""Monitoring and alert routing — the three tables ``monitoring`` owns.

ADR-0009 decision 3 fills the gap ADR-0005 decision 3 left: the alerting surface had no owner and no
named tables. Four shapes here are deliberate and are why this is explicit DDL rather than
autogenerate:

1. **``UNIQUE NULLS NOT DISTINCT`` on both natural keys.** ``tenant_id`` is null until Phase 3, and
   PostgreSQL's default treats two nulls as distinct — so a plain UNIQUE would enforce nothing at
   all today, which is exactly when the dedup guarantee is being built. On ``alerts`` that key is
   what makes "an amendment touching 40 clauses produces one alert, not 40" a property of the
   schema rather than of the code that happens to write it; a re-run of routing over the same
   version updates one row instead of inserting a second. Requires PostgreSQL 15+; the stack is 16.

2. **No fourth table for the clause references.** The clauses an alert covers live in
   ``alerts.clause_references`` (``jsonb``) with their event ids in ``alerts.change_event_ids``
   (``uuid[]``). ADR-0009 gives ``monitoring`` exactly three tables, and these are the alert's
   *content* — never read without it, never joined to anything. The same reasoning keeps impact
   grading on ``alerts`` rather than in a table of its own.

3. **``alert_deliveries`` is an append-only attempt log**, keyed ``(alert_id, subscription_id,
   attempt)``. A mutable status column could say "failed" or "sent" but never "failed twice, then
   succeeded on the third try at 04:12" — which is the whole content of the delivery-failure
   acceptance criterion.

4. **``CHECK (clause_count > 0)`` on ``alerts``.** A renumbering-only amendment produces *no row*
   rather than an empty one (phase1.4 acceptance: it must generate no end-user alert), so an alert
   with nothing behind it is a bug the database refuses rather than an emptiness a reader has to
   interpret.

Foreign keys point at ``cells``, ``documents`` and ``document_versions`` — all ``regulation``-owned,
all in this one database, and read-only from ``monitoring``. The FK is integrity, not ownership;
nothing here writes a ``regulation`` table, and ``change_event_ids`` is an array precisely so that
recording which events composed an alert claims none of them.

Fresh-DB note: every statement uses IF NOT EXISTS / IF EXISTS, so this no-ops on a database already
built from the models and applies cleanly to a live one.

Revision ID: 0006
Revises: 0005
"""

from __future__ import annotations

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

APP_ROLE = "regops_app"

ENUMS: dict[str, tuple[str, ...]] = {
    "alert_channel": ("in_app", "webhook", "email"),
    "alert_severity": ("high", "medium", "low"),
    "alert_status": ("pending", "delivered", "failed"),
    "delivery_status": ("pending", "sent", "failed"),
}

NEW_TABLES = ("alert_subscriptions", "alerts", "alert_deliveries")


def upgrade() -> None:
    for name, values in ENUMS.items():
        labels = ",".join(f"'{v}'" for v in values)
        op.execute(
            f"DO $$ BEGIN CREATE TYPE {name} AS ENUM ({labels}); "
            f"EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
        )

    # --- who hears about what -------------------------------------------------
    #
    # Matching is on **cell** and only on cell (ADR-0009 decision 5). Per ADR-0007 an IR applies to
    # a cell until the Product context exists, so a product column here would encode a precision the
    # data cannot support and would make shared reference data tenant-dependent. Product routing is
    # phase2.2, in `compliance`.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS alert_subscriptions (
            id            uuid           PRIMARY KEY,
            tenant_id     uuid,
            subscriber_id uuid           NOT NULL,
            cell_id       uuid           NOT NULL REFERENCES cells (id),
            channel       alert_channel  NOT NULL DEFAULT 'in_app',
            destination   text,
            min_severity  alert_severity NOT NULL DEFAULT 'low',
            enabled       boolean        NOT NULL DEFAULT true,
            created_at    timestamptz    NOT NULL DEFAULT now(),
            updated_at    timestamptz    NOT NULL DEFAULT now(),
            CONSTRAINT uq_alert_subscriptions_target
                UNIQUE NULLS NOT DISTINCT (tenant_id, subscriber_id, cell_id, channel),
            CONSTRAINT ck_alert_subscriptions_destination_for_remote_channel
                CHECK (channel = 'in_app' OR destination IS NOT NULL)
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_alert_subscriptions_cell_id "
        "ON alert_subscriptions (cell_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_alert_subscriptions_tenant_id "
        "ON alert_subscriptions (tenant_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_alert_subscriptions_subscriber_id "
        "ON alert_subscriptions (subscriber_id);"
    )

    # --- the composed alert ---------------------------------------------------
    #
    # Four timestamps, four different facts (ADR-0003 decision 5 applied to the latency gate).
    # `published_at` is null where the source publishes no date, and latency is then reported
    # *unmeasurable* rather than zero; `retrieved_at` still bounds it from above. All four are
    # copied onto the row because the gate is a claim about what was true when the alert was raised,
    # and a re-parse can change a version's derived fields afterwards.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS alerts (
            id                  uuid           PRIMARY KEY,
            tenant_id           uuid,
            cell_id             uuid           NOT NULL REFERENCES cells (id),
            document_id         uuid           NOT NULL REFERENCES documents (id),
            document_version_id uuid           NOT NULL REFERENCES document_versions (id),
            from_version_id     uuid           REFERENCES document_versions (id),
            severity            alert_severity NOT NULL,
            status              alert_status   NOT NULL DEFAULT 'pending',
            title               text           NOT NULL,
            summary             text           NOT NULL DEFAULT '',
            clause_count        integer        NOT NULL DEFAULT 0,
            change_event_ids    uuid[]         NOT NULL DEFAULT '{}',
            clause_references   jsonb,
            cited_by_locked_ir  boolean        NOT NULL DEFAULT false,
            locked_ir_count     integer        NOT NULL DEFAULT 0,
            published_at        timestamptz,
            retrieved_at        timestamptz,
            detected_at         timestamptz    NOT NULL,
            owner_id            uuid,
            assigned_by         uuid,
            assigned_at         timestamptz,
            created_at          timestamptz    NOT NULL DEFAULT now(),
            CONSTRAINT uq_alerts_target
                UNIQUE NULLS NOT DISTINCT (tenant_id, cell_id, document_version_id),
            CONSTRAINT ck_alerts_clause_count_positive CHECK (clause_count > 0)
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_alerts_cell_id_detected_at ON alerts (cell_id, detected_at);"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_alerts_status ON alerts (status);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_alerts_tenant_id ON alerts (tenant_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_alerts_owner_id ON alerts (owner_id);")

    # --- one row per attempt --------------------------------------------------
    #
    # Written *before* the attempt, so a worker that dies mid-send leaves a `pending` row rather
    # than no trace. `next_retry_at` records when the retry was scheduled for; the retry itself is a
    # Celery countdown, because `monitoring` runs no beat and a sweep would re-discover work that
    # was already scheduled.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS alert_deliveries (
            id              uuid            PRIMARY KEY,
            tenant_id       uuid,
            alert_id        uuid            NOT NULL REFERENCES alerts (id) ON DELETE CASCADE,
            subscription_id uuid            NOT NULL
                                            REFERENCES alert_subscriptions (id) ON DELETE CASCADE,
            channel         alert_channel   NOT NULL,
            destination     text,
            attempt         integer         NOT NULL DEFAULT 1,
            status          delivery_status NOT NULL DEFAULT 'pending',
            error           varchar(512),
            attempted_at    timestamptz     NOT NULL DEFAULT now(),
            delivered_at    timestamptz,
            next_retry_at   timestamptz,
            created_at      timestamptz     NOT NULL DEFAULT now(),
            CONSTRAINT uq_alert_deliveries_attempt UNIQUE (alert_id, subscription_id, attempt),
            CONSTRAINT ck_alert_deliveries_attempt_positive CHECK (attempt >= 1)
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_alert_deliveries_alert_id ON alert_deliveries (alert_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_alert_deliveries_subscription_id "
        "ON alert_deliveries (subscription_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_alert_deliveries_status ON alert_deliveries (status);"
    )

    # --- the seam, enforced by the database ----------------------------------
    #
    # Static review is the phase1.4 acceptance criterion, but a grant is the check that cannot be
    # forgotten under deadline. `monitoring` reads `change_events` and writes nothing in
    # `regulation`; nothing below widens that.
    tables = ", ".join(NEW_TABLES)
    op.execute(
        f"""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                GRANT SELECT, INSERT, UPDATE, DELETE ON {tables} TO {APP_ROLE};
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    for table in reversed(NEW_TABLES):
        op.execute(f"DROP TABLE IF EXISTS {table};")
    for name in ENUMS:
        op.execute(f"DROP TYPE IF EXISTS {name};")
