"""Normalization — the clause store, its diffs, and the change events they emit.

Adds the L2 tables the `regulation` service owns. Four shapes here are deliberate and are why this
is explicit DDL rather than autogenerate:

1. **`clauses` carries `effective_date` *and* `effective_date_phrase` from the first migration.**
   ADR-0003 decision 5 makes the version-level date overridable per clause and
   [ADR-0013](../../../docs/design/ADR-0013-unresolvable-effective-dates.md) pairs every date column
   with its raw-phrase fallback. Adding them after the archive is parsed is the expensive change
   ADR-0002 warns about — every stored citation would have to be invalidated.
2. **No domain-specific column anywhere on `clauses`.** ADR-0002 decision 3 keeps the clause model
   domain-neutral; a Cosmetic-only column here is a phase 1.1 falsifier trigger, not a schema
   detail. `kind` splits prose from table from form — a *content* distinction present in both
   domains.
3. **There is no `annex_rows` table.** An annex table row is a `Clause`
   ([ADR-0014](../../../docs/design/ADR-0014-annex-row-granularity.md)), so the citation contract
   needs no branch and there is no second store to keep in sync. `row_columns` is `jsonb` because
   every table has a different column set.
4. **`irs` / `ir_citations` arrive here but are written by phase 1.2.** 1.1 sets only
   `superseded_at` and `status = stale`, because "amending a cited clause flags the citation
   superseded" is a 1.1 acceptance criterion. `extraction_run_id` and `clause_classifications` are
   left to 1.2 along with the tables they reference.

Fresh-DB note: every statement uses IF NOT EXISTS, so this no-ops on a database already built from
the models and applies cleanly to a live one.

Revision ID: 0003
Revises: 0002
"""

from __future__ import annotations

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

APP_ROLE = "regops_app"

ENUMS: dict[str, tuple[str, ...]] = {
    "clause_kind": ("prose", "heading", "table", "table_row", "form"),
    "change_kind": ("added", "removed", "modified", "renumbered", "moved"),
    "ir_status": ("draft", "locked", "stale", "superseded"),
}

#: Parse-stage drift signals. ADR-0003 decision 6 requires the parse stage to fail closed on these;
#: 0002 created the type with the fetch-stage values only.
NEW_DRIFT_SIGNALS = ("zero_clauses", "clause_count_delta")

NEW_TABLES = (
    "clauses",
    "clause_diffs",
    "change_events",
    "irs",
    "ir_citations",
)


def upgrade() -> None:
    for name, values in ENUMS.items():
        labels = ",".join(f"'{v}'" for v in values)
        op.execute(
            f"DO $$ BEGIN CREATE TYPE {name} AS ENUM ({labels}); "
            f"EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
        )
    for value in NEW_DRIFT_SIGNALS:
        op.execute(f"ALTER TYPE drift_signal ADD VALUE IF NOT EXISTS '{value}';")

    # --- clauses -------------------------------------------------------------
    #
    # Immutable as a parse result: nothing updates a clause's text in place, hence no updated_at.
    # Re-parsing a version deletes its clauses and writes them again (ADR-0015) — a replacement of a
    # derived artefact, not a mutation of evidence. The evidence is the archived bytes.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS clauses (
            id                    uuid         PRIMARY KEY,
            document_version_id   uuid         NOT NULL
                                               REFERENCES document_versions (id) ON DELETE CASCADE,
            clause_path           varchar(512) NOT NULL,
            path_segments         text[]       NOT NULL,
            level                 integer      NOT NULL DEFAULT 1,
            ordinal               integer      NOT NULL DEFAULT 0,
            kind                  clause_kind  NOT NULL DEFAULT 'prose',
            heading               text,
            text                  text         NOT NULL DEFAULT '',
            row_columns           jsonb,
            effective_date        date,
            effective_date_phrase text,
            parent_clause_id      uuid         REFERENCES clauses (id) ON DELETE CASCADE,
            source_ref            varchar(64),
            moved_from_ref        varchar(64),
            moved_to_ref          varchar(64),
            authority_changed     boolean,
            content_hash          varchar(64)  NOT NULL,
            created_at            timestamptz  NOT NULL DEFAULT now(),
            CONSTRAINT uq_clauses_version_path UNIQUE (document_version_id, clause_path)
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_clauses_document_version_id_ordinal "
        "ON clauses (document_version_id, ordinal);"
    )
    # GIN over the segment array is what makes "everything under 제8조" a prefix query rather than a
    # LIKE scan over the rendered path.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_clauses_path_segments ON clauses USING gin (path_segments);"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_clauses_clause_path ON clauses (clause_path);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_clauses_content_hash ON clauses (content_hash);")

    # --- diffs ---------------------------------------------------------------
    #
    # from_version_id is nullable on purpose: the first ingestion of a document is not an amendment,
    # and reporting it as thousands of additions would drown the detection-coverage signal.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS clause_diffs (
            id               uuid         PRIMARY KEY,
            from_version_id  uuid         REFERENCES document_versions (id),
            to_version_id    uuid         NOT NULL REFERENCES document_versions (id),
            clause_path      varchar(512) NOT NULL,
            from_clause_path varchar(512),
            change_kind      change_kind  NOT NULL,
            from_clause_id   uuid         REFERENCES clauses (id) ON DELETE SET NULL,
            to_clause_id     uuid         REFERENCES clauses (id) ON DELETE SET NULL,
            similarity       double precision,
            match_basis      varchar(16),
            needs_review     boolean      NOT NULL DEFAULT false,
            reviewed_at      timestamptz,
            reviewed_by      uuid,
            review_note      text,
            created_at       timestamptz  NOT NULL DEFAULT now(),
            CONSTRAINT uq_clause_diffs_target UNIQUE (to_version_id, clause_path, change_kind)
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_clause_diffs_to_version_id ON clause_diffs (to_version_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_clause_diffs_from_version_id "
        "ON clause_diffs (from_version_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_clause_diffs_needs_review "
        "ON clause_diffs (needs_review) WHERE needs_review;"
    )

    # --- change events -------------------------------------------------------
    #
    # One row per (diff, claiming cell) — ADR-0003 decision 8. `monitoring` reads this one-way by
    # raw SQL and never imports the ORM model. Severity stays null in Phase 1 by decision.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS change_events (
            id             uuid        PRIMARY KEY,
            clause_diff_id uuid        NOT NULL REFERENCES clause_diffs (id) ON DELETE CASCADE,
            cell_id        uuid        NOT NULL REFERENCES cells (id),
            document_id    uuid        NOT NULL REFERENCES documents (id),
            detected_at    timestamptz NOT NULL,
            severity       varchar(16),
            created_at     timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_change_events_diff_cell UNIQUE (clause_diff_id, cell_id)
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_change_events_cell_id_detected_at "
        "ON change_events (cell_id, detected_at);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_change_events_document_id ON change_events (document_id);"
    )

    # --- IR shell (phase 1.2 fills these; 1.1 only supersedes citations) ------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS irs (
            id               uuid        PRIMARY KEY,
            domain_profile   domain      NOT NULL,
            bearer           text,
            modal            varchar(64),
            statement        text        NOT NULL,
            condition_text   text,
            taxonomy_code    varchar(64),
            status           ir_status   NOT NULL DEFAULT 'draft',
            supersedes_ir_id uuid        REFERENCES irs (id),
            stale_since      timestamptz,
            locked_by        uuid,
            locked_at        timestamptz,
            llm_provider     varchar(32),
            llm_model        varchar(64),
            prompt_version   varchar(32),
            rule_version     varchar(32),
            created_at       timestamptz NOT NULL DEFAULT now(),
            updated_at       timestamptz NOT NULL DEFAULT now()
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_irs_status ON irs (status);")

    # A citation is pinned to an immutable version and is never rewritten (ADR-0002 decision 4).
    # An amendment sets superseded_at; the original stays resolvable.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ir_citations (
            id                    uuid         PRIMARY KEY,
            ir_id                 uuid         NOT NULL REFERENCES irs (id) ON DELETE CASCADE,
            document_id           uuid         NOT NULL REFERENCES documents (id),
            document_version_id   uuid         NOT NULL REFERENCES document_versions (id),
            clause_path           varchar(512) NOT NULL,
            effective_date        date,
            superseded_at         timestamptz,
            superseded_by_diff_id uuid         REFERENCES clause_diffs (id) ON DELETE SET NULL,
            created_at            timestamptz  NOT NULL DEFAULT now(),
            CONSTRAINT uq_ir_citations_target UNIQUE (ir_id, document_version_id, clause_path)
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ir_citations_version_path "
        "ON ir_citations (document_version_id, clause_path);"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_ir_citations_ir_id ON ir_citations (ir_id);")

    # --- grants --------------------------------------------------------------
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
    # drift_signal keeps its added labels: PostgreSQL cannot drop an enum value, and the type is
    # still in use by structure_drift_alerts.
