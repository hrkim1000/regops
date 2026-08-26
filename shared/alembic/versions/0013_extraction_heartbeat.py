"""A ``running`` extraction can be checked for a pulse instead of taken at its word.

``extraction_runs.status`` says ``running`` just as firmly whether the worker is mid-clause or was
killed an hour ago, and ``started_at`` cannot tell them apart because it never moves. The row is
therefore load-bearing for two things it cannot support: the UI's *"추출 중"* and the concurrency
guard's 409.

Found the way these things are found. A worker restart on 2026-08-26 killed an extraction at clause
50 of 406 and left the row ``running``; the version was then unextractable until the worker happened
to boot again, because ``_fail_orphaned_runs`` only fires on ``worker_ready``. A worker that stays up
while its task dies has no such event, and would have stranded the version indefinitely.

``heartbeat_at`` is bumped at every incremental checkpoint — the commit that already exists, so this
costs no extra write. Liveness is then *derived* on read (``extraction_run_is_live``) rather than
stored: a second status column would be a copy of this timestamp that starts disagreeing with it the
moment a worker dies, and nothing would run to flip it. Same argument ``version_status`` makes about
``effective_date``.

Existing rows are backfilled to ``coalesce(completed_at, started_at)``, which is honest — it is the
last moment the run is known to have been alive. For the ten completed and two failed rows it
changes nothing; a null would have been read as *not live*, which is also the right answer for them,
but a backfill keeps "null" meaning "column predates this migration" nowhere in the table.

Fresh-DB safe: the baseline builds from the models via ``create_all``, so the column already exists
there and ``ADD COLUMN IF NOT EXISTS`` is a no-op. The backfill only touches rows whose heartbeat is
still null, so re-running it is idempotent.
"""

from __future__ import annotations

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE extraction_runs ADD COLUMN IF NOT EXISTS heartbeat_at TIMESTAMPTZ")
    op.execute(
        "UPDATE extraction_runs "
        "SET heartbeat_at = COALESCE(completed_at, started_at) "
        "WHERE heartbeat_at IS NULL"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE extraction_runs DROP COLUMN IF EXISTS heartbeat_at")
