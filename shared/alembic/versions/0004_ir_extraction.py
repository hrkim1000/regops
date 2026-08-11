"""IR extraction — the extraction run, the classification ledger, and the standard citation.

Fills the ``irs`` / ``ir_citations`` shell 0003 created and adds the three tables ADR-0004's schema
names. Four shapes here are deliberate and are why this is explicit DDL rather than autogenerate:

1. **"An IR without a citation does not exist" becomes structural.** ADR-0004 decision 2 says an
   extraction that cannot attach ``(document_version_id, clause_path)`` is *rejected*, not stored
   with a null citation. A FK cannot express "at least one" in the other direction, so this adds a
   **DEFERRABLE INITIALLY DEFERRED constraint trigger** that fires at commit. Deferred, because the
   IR and its citations are necessarily written in that order inside one transaction; an immediate
   check would reject every legitimate insert. Enforcing it only in the extractor would leave the
   invariant one careless ``session.add`` away from being false, and an uncited IR launders an
   unsourced claim into gap analysis where it looks like a finding.

2. **``clause_classifications`` is keyed per (clause, domain profile), not per clause.** 인체적용
   제품의 위해성평가에 관한 규정 is claimed by both gated cells, and a clause bearing an obligation
   under the SaMD taxonomy may bear none under the Cosmetic one. One shared row would force the two
   readings to agree, which is exactly the domain branch ADR-0004 decision 3 keeps separate.

3. **An ``excluded`` classification must carry a reason**, enforced by CHECK rather than convention.
   "Excluded" with no reason is indistinguishable from "skipped", and the whole point of decision 6
   is that the difference is on the record — coverage is *provable*, not assumed.

4. **``ir_standard_citations`` references, and stores nothing.** It points at
   ``standard_references``, which has no text column and no room for one (ADR-0002 decision 2). Tier
   D body text has nowhere to live in this schema and this migration does not give it one.

Fresh-DB note: every statement uses IF NOT EXISTS / IF EXISTS, so this no-ops on a database already
built from the models and applies cleanly to a live one. The trigger is dropped and recreated
because PostgreSQL has no CREATE TRIGGER IF NOT EXISTS.

Revision ID: 0004
Revises: 0003
"""

from __future__ import annotations

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

APP_ROLE = "regops_app"

ENUMS: dict[str, tuple[str, ...]] = {
    "classification_kind": ("obligation_bearing", "excluded"),
    "exclusion_reason": (
        "definition",
        "scope",
        "heading",
        "permissive",
        "procedural",
        "delegation",
        "table_container",
        "form",
        "empty",
        "no_obligation",
        "unparseable",
    ),
    "extraction_run_status": ("running", "completed", "failed"),
}

NEW_TABLES = (
    "extraction_runs",
    "clause_classifications",
    "ir_standard_citations",
)

#: Raised by the deferred trigger. A distinct SQLSTATE so the service layer can tell "you tried to
#: write an uncited IR" apart from any other integrity error and report the actual reason.
UNCITED_IR_SQLSTATE = "23514"


def upgrade() -> None:
    for name, values in ENUMS.items():
        labels = ",".join(f"'{v}'" for v in values)
        op.execute(
            f"DO $$ BEGIN CREATE TYPE {name} AS ENUM ({labels}); "
            f"EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
        )

    # --- extraction runs -----------------------------------------------------
    #
    # The provenance anchor ADR-0008 requires of an *agent*: it invokes an LLM, writes rows carrying
    # provenance, and cannot be trusted without a separate check. `temperature` is stored rather
    # than assumed — ADR-0017 pins it to 0 and calls drift a regression, which is only checkable if
    # the value actually used is on the row.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS extraction_runs (
            id                  uuid                  PRIMARY KEY,
            document_version_id uuid                  NOT NULL
                                                      REFERENCES document_versions (id)
                                                      ON DELETE CASCADE,
            domain_profile      domain                NOT NULL,
            rule_version        varchar(32)           NOT NULL,
            prompt_version      varchar(32)           NOT NULL,
            llm_provider        varchar(32)           NOT NULL,
            llm_model           varchar(64)           NOT NULL,
            temperature         double precision,
            status              extraction_run_status NOT NULL DEFAULT 'running',
            clauses_seen        integer               NOT NULL DEFAULT 0,
            irs_written         integer               NOT NULL DEFAULT 0,
            rejected_uncited    integer               NOT NULL DEFAULT 0,
            started_at          timestamptz           NOT NULL,
            completed_at        timestamptz,
            error               text,
            CONSTRAINT ck_extraction_runs_counts_nonneg
                CHECK (clauses_seen >= 0 AND irs_written >= 0 AND rejected_uncited >= 0)
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_extraction_runs_version "
        "ON extraction_runs (document_version_id, started_at);"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_extraction_runs_status ON extraction_runs (status);")

    # --- irs.extraction_run_id ----------------------------------------------
    op.execute("ALTER TABLE irs ADD COLUMN IF NOT EXISTS extraction_run_id uuid;")
    op.execute(
        """
        DO $$ BEGIN
            ALTER TABLE irs ADD CONSTRAINT irs_extraction_run_id_fkey
                FOREIGN KEY (extraction_run_id) REFERENCES extraction_runs (id) ON DELETE SET NULL;
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_irs_extraction_run_id ON irs (extraction_run_id);")
    # Re-derivation walks the chain backwards from the newest IR (ADR-0004 decision 5), and a stale
    # sweep looks up "the IR that cites this clause" through ir_citations. Both are hot enough to
    # index; supersedes_ir_id had none because 1.1 never wrote it.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_irs_supersedes_ir_id ON irs (supersedes_ir_id) "
        "WHERE supersedes_ir_id IS NOT NULL;"
    )

    # --- clause classifications ---------------------------------------------
    #
    # Every clause is examined and gets a row (ADR-0004 decision 6). Without this, "50 IRs from 200
    # clauses" cannot be told apart from 150 missed obligations.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS clause_classifications (
            id                uuid                PRIMARY KEY,
            clause_id         uuid                NOT NULL
                                                  REFERENCES clauses (id) ON DELETE CASCADE,
            domain_profile    domain              NOT NULL,
            kind              classification_kind NOT NULL,
            exclusion_reason  exclusion_reason,
            exclusion_note    text,
            extraction_run_id uuid                REFERENCES extraction_runs (id) ON DELETE SET NULL,
            classified_by     uuid,
            classified_at     timestamptz         NOT NULL,
            CONSTRAINT uq_clause_classifications_target UNIQUE (clause_id, domain_profile),
            CONSTRAINT ck_clause_classifications_reason
                CHECK ((kind = 'excluded') = (exclusion_reason IS NOT NULL))
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_clause_classifications_run "
        "ON clause_classifications (extraction_run_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_clause_classifications_kind "
        "ON clause_classifications (kind);"
    )

    # --- IR → standard citation ---------------------------------------------
    #
    # ON DELETE RESTRICT, not CASCADE: a recognition record that an IR depends on must not vanish
    # silently. If a standard is withdrawn, the recognition row's `status` says so — deleting it
    # would take the evidence with it.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ir_standard_citations (
            id                    uuid        PRIMARY KEY,
            ir_id                 uuid        NOT NULL REFERENCES irs (id) ON DELETE CASCADE,
            standard_reference_id uuid        NOT NULL
                                              REFERENCES standard_references (id) ON DELETE RESTRICT,
            reference_text        text,
            created_at            timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_ir_standard_citations_target UNIQUE (ir_id, standard_reference_id)
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ir_standard_citations_ir_id "
        "ON ir_standard_citations (ir_id);"
    )

    # --- the uncited-IR guard ------------------------------------------------
    #
    # Deferred to commit, because an IR row necessarily precedes its citations inside one
    # transaction. Checked from both sides: inserting an IR that never gets a citation, and deleting
    # the last citation off one that already exists. The delete side skips rows whose IR is also
    # gone — a CASCADE from `irs` removes the citations, and that is a deletion, not a violation.
    #
    # **The branch has to be an IF, not a SQL CASE.** One function serves two tables, so `OLD` is an
    # `irs` record on one trigger and an `ir_citations` record on the other. PL/pgSQL prepares an
    # expression whole, and `CASE WHEN TG_OP='DELETE' THEN OLD.ir_id ELSE NEW.id END` therefore
    # type-checks `OLD.ir_id` on the `irs` trigger too — where no such field exists, failing every
    # legitimate insert with `record "old" has no field "ir_id"`. Statements inside an IF are
    # compiled on first execution of that branch, so only the reachable field is ever resolved.
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION assert_ir_has_citation() RETURNS trigger AS $$
        DECLARE
            target uuid;
        BEGIN
            IF TG_OP = 'DELETE' THEN
                target := OLD.ir_id;
            ELSE
                target := NEW.id;
            END IF;

            -- The check is deferred to commit, so the row it was queued for may have been deleted
            -- since — by a CASCADE from `irs`, or by a later statement in the same transaction.
            -- An IR that no longer exists cannot be an uncited IR, and asserting about one turns
            -- ordinary cleanup ("unlink, then delete") into a spurious violation.
            IF NOT EXISTS (SELECT 1 FROM irs WHERE id = target) THEN
                RETURN NULL;
            END IF;

            IF NOT EXISTS (SELECT 1 FROM ir_citations WHERE ir_id = target) THEN
                RAISE EXCEPTION
                    'IR % has no citation; an IR without a citation does not exist '
                    '(ADR-0004 decision 2)', target
                    USING ERRCODE = '{UNCITED_IR_SQLSTATE}';
            END IF;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute("DROP TRIGGER IF EXISTS trg_irs_require_citation ON irs;")
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER trg_irs_require_citation
            AFTER INSERT OR UPDATE ON irs
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION assert_ir_has_citation();
        """
    )
    op.execute("DROP TRIGGER IF EXISTS trg_ir_citations_require_citation ON ir_citations;")
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER trg_ir_citations_require_citation
            AFTER DELETE ON ir_citations
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION assert_ir_has_citation();
        """
    )

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
    op.execute("DROP TRIGGER IF EXISTS trg_ir_citations_require_citation ON ir_citations;")
    op.execute("DROP TRIGGER IF EXISTS trg_irs_require_citation ON irs;")
    op.execute("DROP FUNCTION IF EXISTS assert_ir_has_citation();")

    op.execute("ALTER TABLE irs DROP CONSTRAINT IF EXISTS irs_extraction_run_id_fkey;")
    op.execute("DROP INDEX IF EXISTS ix_irs_extraction_run_id;")
    op.execute("DROP INDEX IF EXISTS ix_irs_supersedes_ir_id;")
    op.execute("ALTER TABLE irs DROP COLUMN IF EXISTS extraction_run_id;")

    for table in reversed(NEW_TABLES):
        op.execute(f"DROP TABLE IF EXISTS {table};")
    for name in ENUMS:
        op.execute(f"DROP TYPE IF EXISTS {name};")
