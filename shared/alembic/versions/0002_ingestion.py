"""Ingestion — source registry, WORM-backed versions, and the record of every fetch.

Adds the L1 tables the `regulation` service owns: the source registry and its schedule, the
observation written on every fetch attempt, documents and their immutable versions, annex file
links, Tier D recognition records, drift alerts, and discovery runs.

Three shapes here are deliberate and are the reason this is explicit DDL rather than autogenerate:

1. **`fetch_observations` has no request-URL column.** 국가법령정보 authenticates by query-string
   key; the trail is append-only and outlives any rotation, so a credential written into it could
   never be cleaned up (ADR-0003 decision 13). The column simply does not exist.
2. **`standard_references` has no `text` column and no varchar over 512.** Tier D is enforced by
   there being nowhere to put a standard's body text, not by policy (ADR-0002 decision 2).
3. **Annexes are child `documents`, not rows on a version.** 별표 carry their own effective dates
   and must version independently of the parent body; a child row of `document_versions` cannot
   (ADR-0012). `documents.parent_document_id` + `annex_no` carry that instead.

Fresh-DB note: every statement uses IF NOT EXISTS, so this no-ops on a database already built from
the models and applies cleanly to a live one.

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

APP_ROLE = "regops_app"

ENUMS: dict[str, tuple[str, ...]] = {
    "source_block": (
        "primary_laws",
        "regulations",
        "standards",
        "guidance",
        "registration",
        "ingredient",
        "gmp",
        "safety",
        "official_sources",
    ),
    "source_tier": ("a", "b", "c", "d"),
    "fetch_outcome": ("changed", "unchanged", "not_modified", "skipped", "error"),
    "drift_signal": (
        "zero_records",
        "record_count_delta",
        "missing_root",
        "auth_failure",
        "empty_annex_body",
    ),
    "doc_type": (
        "law",
        "decree",
        "enforcement_rule",
        "notice",
        "annex",
        "guidance",
        "feed",
    ),
    "attachment_kind": ("annex_file", "form", "other"),
    "standard_status": ("recognized", "harmonized", "withdrawn", "superseded", "unknown"),
}

NEW_TABLES = (
    "sources",
    "source_schedules",
    "fetch_observations",
    "structure_drift_alerts",
    "source_discovery_runs",
    "documents",
    "document_cells",
    "document_versions",
    "attachments",
    "standard_references",
)


def upgrade() -> None:
    for name, values in ENUMS.items():
        labels = ",".join(f"'{v}'" for v in values)
        op.execute(
            f"DO $$ BEGIN CREATE TYPE {name} AS ENUM ({labels}); "
            f"EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
        )

    # --- source registry -----------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS sources (
            id                        uuid PRIMARY KEY,
            slug                      varchar(160)  NOT NULL,
            cell_id                   uuid          NOT NULL REFERENCES cells (id),
            block                     source_block  NOT NULL,
            ordinal                   integer       NOT NULL DEFAULT 0,
            title                     text          NOT NULL,
            url_template              text,
            tier                      source_tier   NOT NULL,
            ingestible                boolean       NOT NULL DEFAULT true,
            connector                 varchar(64),
            params                    jsonb         NOT NULL DEFAULT '{}'::jsonb,
            interval_override_seconds integer,
            interval_override_reason  text,
            http_etag                 varchar(255),
            http_last_modified        varchar(64),
            notes                     text,
            created_at                timestamptz   NOT NULL DEFAULT now(),
            updated_at                timestamptz   NOT NULL DEFAULT now(),
            CONSTRAINT uq_sources_slug UNIQUE (slug),
            -- An override is a decision; a decision without a recorded reason is an accident.
            CONSTRAINT ck_sources_override_reason CHECK (
                (interval_override_seconds IS NULL) = (interval_override_reason IS NULL)
            )
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_sources_cell_id_block ON sources (cell_id, block);")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS source_schedules (
            source_id            uuid        PRIMARY KEY
                                             REFERENCES sources (id) ON DELETE CASCADE,
            interval_seconds     integer     NOT NULL,
            next_due_at          timestamptz NOT NULL,
            last_started_at      timestamptz,
            last_completed_at    timestamptz,
            enabled              boolean     NOT NULL DEFAULT true,
            consecutive_failures integer     NOT NULL DEFAULT 0,
            created_at           timestamptz NOT NULL DEFAULT now(),
            updated_at           timestamptz NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_source_schedules_due "
        "ON source_schedules (next_due_at) WHERE enabled;"
    )

    # --- observations (written on EVERY attempt, ADR-0003 decision 3) --------
    #
    # No resolved-URL column. See the module docstring.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS fetch_observations (
            id                uuid          PRIMARY KEY,
            source_id         uuid          NOT NULL REFERENCES sources (id),
            fetched_at        timestamptz   NOT NULL,
            http_status       integer,
            content_hash      varchar(64),
            connector_version varchar(32)   NOT NULL,
            outcome           fetch_outcome NOT NULL,
            published_at      timestamptz,
            artifact_count    integer       NOT NULL DEFAULT 0,
            duration_ms       integer,
            notes             text,
            created_at        timestamptz   NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_fetch_observations_source_id_fetched_at "
        "ON fetch_observations (source_id, fetched_at);"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS structure_drift_alerts (
            id              uuid         PRIMARY KEY,
            source_id       uuid         NOT NULL REFERENCES sources (id),
            detected_at     timestamptz  NOT NULL,
            signal          drift_signal NOT NULL,
            expected        text,
            actual          text,
            resolved_at     timestamptz,
            resolved_by     uuid,
            resolution_note text,
            created_at      timestamptz  NOT NULL DEFAULT now(),
            updated_at      timestamptz  NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_structure_drift_alerts_source_id_resolved_at "
        "ON structure_drift_alerts (source_id, resolved_at);"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS source_discovery_runs (
            id             uuid        PRIMARY KEY,
            authority      authority   NOT NULL,
            ran_at         timestamptz NOT NULL,
            upstream_count integer     NOT NULL DEFAULT 0,
            matched        integer     NOT NULL DEFAULT 0,
            unmatched      integer     NOT NULL DEFAULT 0,
            details        jsonb       NOT NULL DEFAULT '{}'::jsonb,
            created_at     timestamptz NOT NULL DEFAULT now()
        );
        """
    )

    # --- documents -----------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS documents (
            id                 uuid         PRIMARY KEY,
            canonical_key      varchar(255) NOT NULL,
            title              text         NOT NULL,
            doc_type           doc_type     NOT NULL,
            issuing_authority  varchar(128),
            parent_document_id uuid         REFERENCES documents (id),
            annex_no           varchar(32),
            source_id          uuid         REFERENCES sources (id),
            created_at         timestamptz  NOT NULL DEFAULT now(),
            updated_at         timestamptz  NOT NULL DEFAULT now(),
            CONSTRAINT uq_documents_canonical_key UNIQUE (canonical_key),
            -- An annex is a child document; anything else must not claim a parent.
            CONSTRAINT ck_documents_annex_parent CHECK (
                (doc_type = 'annex') = (parent_document_id IS NOT NULL)
            )
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_documents_parent_document_id "
        "ON documents (parent_document_id);"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS document_cells (
            document_id uuid        NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
            cell_id     uuid        NOT NULL REFERENCES cells (id),
            created_at  timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (document_id, cell_id)
        );
        """
    )

    # Immutable once written (ADR-0002 decision 4) — hence no updated_at.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS document_versions (
            id                    uuid        PRIMARY KEY,
            document_id           uuid        NOT NULL REFERENCES documents (id),
            version_group_id      uuid        NOT NULL,
            version_label         varchar(64),
            language              varchar(8)  NOT NULL DEFAULT 'ko',
            content_hash          varchar(64) NOT NULL,
            raw_object_key        varchar(160) NOT NULL,
            raw_bytes             integer     NOT NULL DEFAULT 0,
            content_type          varchar(128),
            retrieved_at          timestamptz NOT NULL,
            published_at          timestamptz,
            effective_date        date,
            effective_date_phrase text,
            parser_version        varchar(32),
            fetch_observation_id  uuid        REFERENCES fetch_observations (id),
            created_at            timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_document_versions_content UNIQUE (document_id, language, content_hash)
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_document_versions_document_id_retrieved_at "
        "ON document_versions (document_id, retrieved_at);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_document_versions_version_group_id "
        "ON document_versions (version_group_id);"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS attachments (
            id                  uuid            PRIMARY KEY,
            document_version_id uuid            NOT NULL
                                                REFERENCES document_versions (id) ON DELETE CASCADE,
            kind                attachment_kind NOT NULL,
            title               text,
            ordinal             integer         NOT NULL DEFAULT 0,
            file_format         varchar(16),
            source_url          text,
            content_hash        varchar(64),
            raw_object_key      varchar(160),
            created_at          timestamptz     NOT NULL DEFAULT now(),
            updated_at          timestamptz     NOT NULL DEFAULT now(),
            CONSTRAINT uq_attachments_version_kind_ordinal
                UNIQUE (document_version_id, kind, ordinal)
        );
        """
    )

    # --- Tier D --------------------------------------------------------------
    #
    # Every column is typed or a bounded varchar <= 512. There is no text column, and
    # tests/unit/test_tier_d.py fails if one is added. That is the mechanism; the CI string scan
    # is the backstop.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS standard_references (
            id                 uuid            PRIMARY KEY,
            number             varchar(64)     NOT NULL,
            edition            varchar(32),
            issuing_body       varchar(64),
            recognition_number varchar(64),
            title              varchar(512),
            effective_date     date,
            withdrawal_date    date,
            status             standard_status NOT NULL DEFAULT 'unknown',
            official_url       varchar(512),
            cell_id            uuid            REFERENCES cells (id),
            source_id          uuid            REFERENCES sources (id),
            last_seen_at       timestamptz,
            created_at         timestamptz     NOT NULL DEFAULT now(),
            updated_at         timestamptz     NOT NULL DEFAULT now(),
            CONSTRAINT uq_standard_references_identity
                UNIQUE (number, edition, recognition_number)
        );
        """
    )

    # --- grants --------------------------------------------------------------
    #
    # Regulation data is shared reference data, fully writable by the app role. The append-only
    # restriction is audit_log's alone (migration 0001).
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
