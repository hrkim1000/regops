"""``document_versions.authority_removed_paths`` — the removal the authority stated.

ADR-0018 decision 8 accepts a cost and names its mitigation in the same breath: FDA states
*removal* but not *movement*, so CFR redesignation falls to ADR-0002 decision 7's
content-similarity fallback — and *"the `removed` flag helps: it distinguishes 'the authority
deleted this' from 'our differ lost it', which MFDS never had to."*

The flag was being read and then dropped. ``ecfr.py`` computed ``removed_sections`` into
``FetchedArtifact.meta``, and meta reaches nothing durable (phase2.0a *Deviations* 10) — grep found
its only consumer was one assertion in a connector test. So the mitigation existed on paper and the
differ never saw it, which matters because ``RENUMBER_MATCH_RATIO`` is 0.60: a genuinely deleted
section only has to resemble some surviving section by 60% to be reported as a renumber, and a
deletion reported as a renumber is an alert the subscriber never receives.

A named column rather than a generic ``meta`` blob, following ADR-0019: that decision gave the
Federal Register's records typed tables instead of widening the store with somewhere to put
anything. The generic connector-meta gap stays open and stays recorded.

Nullable, and null is the normal case. law.go.kr supplies 조문이동이전 / 조문이동이후, so an MFDS
move is *stated* and never reaches the fallback this column feeds; every MFDS version keeps a null
here and behaves exactly as it did.

``clause_diffs.match_basis`` widens 16 -> 32 in the same change, because it is the same change:
the new basis this enables is ``similarity_contested`` (20 characters), which did not fit. Widening
a ``varchar`` is a catalogue update in Postgres — no table rewrite, no lock worth naming — and the
alternative was choosing the value's name to fit a width nobody had reasoned about.

Fresh-DB safe: the baseline builds from the models via ``create_all``, so both shapes are already
present there, and ``IF NOT EXISTS`` plus an idempotent ``TYPE`` change make this a no-op.

Revision ID: 0011
Revises: 0010
"""

from __future__ import annotations

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE document_versions ADD COLUMN IF NOT EXISTS authority_removed_paths jsonb;"
    )
    op.execute("ALTER TABLE clause_diffs ALTER COLUMN match_basis TYPE character varying(32);")


def downgrade() -> None:
    op.execute("ALTER TABLE document_versions DROP COLUMN IF EXISTS authority_removed_paths;")
    # Not narrowed back: any row written under this revision may hold a value longer than 16, and
    # a downgrade that truncates evidence is worse than one that leaves a column roomier.
