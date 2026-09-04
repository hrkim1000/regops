"""A resumed run records what it resumed, so a chain of them is legible.

Resumption picked the single most recent run for the ``(version, domain)`` and cleared every other
run's drafts, on the reasoning that an older run's drafts had since been cleared by whatever ran
after it. That reasoning is false the moment a resume happens: a resuming run **keeps** its
predecessor's drafts — that is the whole point of it — so the run before last is alive, not
superseded.

Found by doing it. 21 U.S.C. chapter 9 crashed twice, and the third run adopted only the 1,400
clauses of the second while treating the first as stale: it deleted **938 IRs** that were still the
only extraction those 2,625 clauses had. Worse than the loss is the shape of it — with a crash
roughly every hundred minutes, every resume destroyed the segment before it, so a run that was
interrupted twice could never converge.

``resumed_from_id`` makes the chain a fact on the row instead of an inference from timestamps.
``_resumable_run`` still picks one predecessor; what changes is that the caller can now walk
backwards from it and adopt — and spare the drafts of — every run in the chain.

``ON DELETE SET NULL`` rather than CASCADE: deleting a run is not a reason to delete the runs it
inherited from, and a broken link should degrade the chain to "unknown predecessor" rather than
remove history.

Fresh-DB safe: the baseline builds from the models via ``create_all``, so the column and its
constraint already exist there and both statements are no-ops. Nothing is backfilled — a run that
predates this column has no recorded predecessor, and null is the honest answer rather than a guess
reconstructed from `started_at` ordering, which is exactly the inference this migration exists to
stop trusting.
"""

from __future__ import annotations

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE extraction_runs ADD COLUMN IF NOT EXISTS resumed_from_id UUID")
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'fk_extraction_runs_resumed_from_id_extraction_runs'
            ) THEN
                ALTER TABLE extraction_runs
                    ADD CONSTRAINT fk_extraction_runs_resumed_from_id_extraction_runs
                    FOREIGN KEY (resumed_from_id) REFERENCES extraction_runs (id)
                    ON DELETE SET NULL;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE extraction_runs DROP COLUMN IF EXISTS resumed_from_id")
