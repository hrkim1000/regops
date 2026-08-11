"""Retrieval and citation-enforced Q&A — the ``assistant`` service's own tables.

Five shapes here are deliberate and are why this is explicit DDL rather than autogenerate:

1. **``CREATE EXTENSION vector``, which means the database image changed.** Stock
   ``postgres:16-alpine`` has no pgvector, so docker-compose's ``db`` is now ``pgvector/pgvector:pg16``
   — the same PostgreSQL major version reading the same data directory, but Debian/glibc where that
   was Alpine/musl. glibc and musl collate text differently, so every text index built under the old
   image is sorted by rules the new one does not share. This migration therefore **reindexes**, once,
   at the end. Skipping it leaves indexes that answer range and ordering queries with stale
   comparisons — the kind of wrong that returns *fewer* rows rather than an error.

2. **Embeddings are owned by ``assistant``, not by ``regulation``.** ``clause_embeddings``
   references ``clauses`` and lives here, so swapping the embedding model is a change in one service
   rather than a migration against the clause store (ADR-0006; CLAUDE.md § Table ownership). The
   HNSW index is cosine, matching the distance the retrieval arm actually queries with — an index
   built for a different operator class is silently never used.

3. **A lexical index on ``clauses``, owned by the migration history rather than by a service.**
   Hybrid retrieval (ADR-0006 decision 3) needs BM25-style search over clause text, and regulatory
   corpora are identifier-dense enough that a vector-only design underperforms on exactly the
   questions RA staff ask most. ``assistant`` reads ``clauses`` one-way by raw SQL, the same way
   ``monitoring`` reads ``change_events``; this index is a read-side optimization for that path and
   adds no column to the clause store. The configuration is ``simple`` because PostgreSQL ships no
   Korean stemmer, and any other configuration would stem the English tokens in a Korean corpus and
   leave the rest alone.

4. **``answer_citations`` is a separate table from ``ir_citations``** (ADR-0006 decision 10). They
   share a shape and nothing else: an amended clause makes an IR *stale* and re-derived, and an
   answer *superseded* and re-verified. One table would couple the answer log to the obligation
   model and let a single amendment rewrite history in both.

5. **``answers.confidence`` is CHECK-bounded to [0, 1].** The sub-threshold route to human review is
   a product guarantee; a confidence that can hold 1.7 makes the threshold comparison meaningless
   without anything failing.

Fresh-DB note: every statement uses IF NOT EXISTS / IF EXISTS, so this no-ops on a database already
built from the models and applies cleanly to a live one.

Revision ID: 0005
Revises: 0004
"""

from __future__ import annotations

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

APP_ROLE = "regops_app"

#: Must match ``regops_shared.constants.EMBEDDING_DIM``. Pinned in both places on purpose: the
#: column width is a storage fact and the constant is a client fact, and a mismatch has to fail at
#: the first insert rather than be papered over by a cast.
EMBEDDING_DIM = 768

#: Must match ``regops_shared.constants.FTS_CONFIG``.
FTS_CONFIG = "simple"

ENUMS: dict[str, tuple[str, ...]] = {
    "embedding_scope": ("article", "article_fragment", "table_header", "form"),
    "answer_status": ("answered", "needs_verification", "needs_review"),
    "verification_verdict": ("supported", "partial", "unsupported"),
}

NEW_TABLES = (
    "clause_embeddings",
    "queries",
    "answers",
    "answer_citations",
    "verification_results",
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    for name, values in ENUMS.items():
        labels = ",".join(f"'{v}'" for v in values)
        op.execute(
            f"DO $$ BEGIN CREATE TYPE {name} AS ENUM ({labels}); "
            f"EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
        )

    # --- the retrieval index -------------------------------------------------
    #
    # One row per *passage*, which is a 조 with its 항/호/목 rolled in (ADR-0006 decision 1), not one
    # row per clause. `child_clause_paths` is what lets citation stay finer than retrieval: the
    # passage names every clause folded into it, so generation can cite 제8조제2항제3호 from a match
    # that only ever had to find 제8조.
    #
    # Annex table *rows* never reach this table at all (decision 2) — thousands of near-identical
    # ingredient lines cluster so tightly that similarity becomes noise. The table's title and
    # column labels are embedded instead, and the lookup that follows is relational.
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS clause_embeddings (
            id                  uuid            PRIMARY KEY,
            clause_id           uuid            NOT NULL
                                                REFERENCES clauses (id) ON DELETE CASCADE,
            document_version_id uuid            NOT NULL
                                                REFERENCES document_versions (id) ON DELETE CASCADE,
            scope               embedding_scope NOT NULL,
            fragment_index      integer         NOT NULL DEFAULT 0,
            passage             text            NOT NULL,
            child_clause_paths  text[]          NOT NULL DEFAULT '{{}}',
            content_hash        varchar(64)     NOT NULL,
            embedding           vector({EMBEDDING_DIM}) NOT NULL,
            model               varchar(64)     NOT NULL,
            dim                 integer         NOT NULL DEFAULT {EMBEDDING_DIM},
            passage_version     varchar(32)     NOT NULL,
            created_at          timestamptz     NOT NULL DEFAULT now(),
            CONSTRAINT uq_clause_embeddings_fragment UNIQUE (clause_id, fragment_index),
            CONSTRAINT ck_clause_embeddings_fragment_index_nonneg CHECK (fragment_index >= 0)
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_clause_embeddings_version "
        "ON clause_embeddings (document_version_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_clause_embeddings_model ON clause_embeddings (model);"
    )
    # Cosine, matching the `<=>` operator retrieval queries with. An HNSW index built for a
    # different operator class is not an error — it is simply never chosen, and the only symptom is
    # a sequential scan nobody notices until the corpus grows.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_clause_embeddings_hnsw ON clause_embeddings "
        "USING hnsw (embedding vector_cosine_ops);"
    )

    # --- the lexical arm, over the clause store ------------------------------
    op.execute(
        f"CREATE INDEX IF NOT EXISTS ix_clauses_fts ON clauses USING gin "
        f"(to_tsvector('{FTS_CONFIG}', coalesce(heading, '') || ' ' || coalesce(text, '')));"
    )

    # --- the answer log ------------------------------------------------------
    #
    # `cell_id` is NOT NULL: retrieval is cell-scoped (decision 9) and a nullable cell would make
    # "unscoped" the accidental default, which is how a cosmetic question gets answered from device
    # regulation. Cross-cell is the explicit, recorded opt-in beside it.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS queries (
            id         uuid        PRIMARY KEY,
            tenant_id  uuid,
            cell_id    uuid        NOT NULL REFERENCES cells (id),
            cross_cell boolean     NOT NULL DEFAULT false,
            text       text        NOT NULL,
            asked_by   uuid,
            asked_at   timestamptz NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_queries_cell_asked_at ON queries (cell_id, asked_at);"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_queries_tenant_id ON queries (tenant_id);")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS answers (
            id                       uuid          PRIMARY KEY,
            query_id                 uuid          NOT NULL
                                                   REFERENCES queries (id) ON DELETE CASCADE,
            tenant_id                uuid,
            text                     text          NOT NULL DEFAULT '',
            status                   answer_status NOT NULL,
            confidence               double precision NOT NULL DEFAULT 0,
            no_answer_reason         varchar(32),
            document_version_scope   uuid[]        NOT NULL DEFAULT '{}',
            effective_date_scope     date,
            straddles_effective_date boolean       NOT NULL DEFAULT false,
            llm_provider             varchar(32)   NOT NULL,
            llm_model                varchar(64)   NOT NULL,
            prompt_version           varchar(32)   NOT NULL,
            retrieval_version        varchar(32)   NOT NULL,
            superseded_at            timestamptz,
            created_at               timestamptz   NOT NULL DEFAULT now(),
            CONSTRAINT ck_answers_confidence_range CHECK (confidence >= 0 AND confidence <= 1)
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_answers_query_id ON answers (query_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_answers_status ON answers (status);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_answers_tenant_id ON answers (tenant_id);")

    # `claim_index` ties a citation to the sentence it supports, not to the answer as a whole. The
    # verification pass judges claims one at a time, and an answer-level citation would make
    # "which claim is unsupported" unanswerable.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS answer_citations (
            id                    uuid        PRIMARY KEY,
            answer_id             uuid        NOT NULL REFERENCES answers (id) ON DELETE CASCADE,
            claim_index           integer     NOT NULL DEFAULT 0,
            document_id           uuid        NOT NULL REFERENCES documents (id),
            document_version_id   uuid        NOT NULL REFERENCES document_versions (id),
            clause_path           varchar(512) NOT NULL,
            effective_date        date,
            superseded_at         timestamptz,
            superseded_by_diff_id uuid        REFERENCES clause_diffs (id) ON DELETE SET NULL,
            created_at            timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_answer_citations_target
                UNIQUE (answer_id, claim_index, document_version_id, clause_path)
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_answer_citations_answer_id ON answer_citations (answer_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_answer_citations_version_path "
        "ON answer_citations (document_version_id, clause_path);"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS verification_results (
            id                uuid                 PRIMARY KEY,
            answer_id         uuid                 NOT NULL
                                                   REFERENCES answers (id) ON DELETE CASCADE,
            claim_index       integer              NOT NULL,
            verdict           verification_verdict NOT NULL,
            reason            text,
            verifier_provider varchar(32)          NOT NULL,
            verifier_model    varchar(64)          NOT NULL,
            prompt_version    varchar(32)          NOT NULL,
            created_at        timestamptz          NOT NULL DEFAULT now(),
            CONSTRAINT uq_verification_results_claim UNIQUE (answer_id, claim_index)
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_verification_results_verdict "
        "ON verification_results (verdict);"
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

    _reindex_after_collation_change()


def _reindex_after_collation_change() -> None:
    """Rebuild every index once, because the C library that orders text changed underneath them.

    ``REINDEX DATABASE`` cannot run inside a transaction block and Alembic runs migrations in one,
    so this walks the tables instead — ``REINDEX TABLE`` is transaction-safe. At the gated corpus's
    size (25,729 clauses) the whole pass is seconds, and doing it here rather than in a runbook
    means a developer who pulls this change and runs the documented ``docker compose run --rm
    migrate`` gets a consistent database without knowing why it was needed.

    ``ALTER DATABASE ... REFRESH COLLATION VERSION`` then clears the version-mismatch warning that
    PostgreSQL would otherwise print on every connection. It is guarded: on a database that never
    saw the old image there is nothing to refresh, and that is not a failure.
    """
    op.execute(
        """
        DO $$
        DECLARE
            target text;
        BEGIN
            FOR target IN
                SELECT quote_ident(schemaname) || '.' || quote_ident(tablename)
                FROM pg_tables WHERE schemaname = 'public'
            LOOP
                EXECUTE 'REINDEX TABLE ' || target;
            END LOOP;
        END $$;
        """
    )
    op.execute(
        """
        DO $$ BEGIN
            EXECUTE 'ALTER DATABASE ' || quote_ident(current_database())
                 || ' REFRESH COLLATION VERSION';
        EXCEPTION WHEN OTHERS THEN NULL; END $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_clauses_fts;")
    for table in reversed(NEW_TABLES):
        op.execute(f"DROP TABLE IF EXISTS {table};")
    for name in ENUMS:
        op.execute(f"DROP TYPE IF EXISTS {name};")
    # The extension is left in place: dropping it would take the `vector` type with it, and nothing
    # else in this schema depends on its absence.
