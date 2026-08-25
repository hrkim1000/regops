"""A second full-text index, stemmed for English.

``FTS_CONFIG`` is ``simple`` — no stemming — and that is correct for Korean, which Postgres has no
stemmer for. It is wrong for English, and measurably so. Over the 14 parsed FDA versions on
2026-08-25:

===============  ========  =========  ======
term             simple    english    change
===============  ========  =========  ======
``requirement``       258      2,009   +679%
``label``             185        696   +276%
``record``             96        332   +246%
``manufacturer``      495      1,066   +115%
``device``          1,564      1,817    +16%
===============  ========  =========  ======

``requirement`` and ``requirements`` are unrelated tokens under ``simple``, so the lexical arm of a
hybrid retrieval loses most of its recall on exactly the vocabulary a regulatory corpus is built
from. Identifier lookup is a golden-set axis and so is free-text recall; this is a gate input.

**The Korean path is untouched, structurally rather than by testing for it.** The existing
unconditional ``simple`` index from 0005 stays exactly as it is, and this adds a second index beside
it. A Korean query runs the same SQL against the same index with the same configuration it always
did, so there is nothing for a before-and-after to detect. Only a query whose scope is English
selects the new configuration.

An unconditional index rather than one partial on language: ``clauses`` carries no language column —
language lives on ``document_versions`` — and a partial index's predicate must be on the indexed
table. Denormalising a column onto ~40,000 clause rows to save an index that costs a few tens of
megabytes is the more invasive of the two, and it would put a value on ``clauses`` that can disagree
with the version it came from.

Not ``CONCURRENTLY``: Alembic runs migrations inside a transaction and ``CREATE INDEX CONCURRENTLY``
cannot. At this corpus size the lock is momentary. If the clause store ever grows to where that is
not true, this index should be created out of band rather than this migration being made clever.

Revision ID: 0010
Revises: 0009
"""

from __future__ import annotations

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

INDEX_NAME = "ix_clauses_fts_english"
#: Must match the expression ``assistant``'s lexical arm builds, or the index is never chosen.
EXPRESSION = "to_tsvector('english', coalesce(heading, '') || ' ' || coalesce(text, ''))"


def upgrade() -> None:
    op.execute(f"CREATE INDEX IF NOT EXISTS {INDEX_NAME} ON clauses USING gin ({EXPRESSION});")


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {INDEX_NAME};")
