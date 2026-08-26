"""An RA can refuse a draft IR, and the refusal is a state rather than an absence.

ADR-0020. [ADR-0004](../../../docs/design/ADR-0004-ir-extraction-and-domain-branching.md) decision 4
describes the lifecycle as *"an RA reviews and locks"* and says nothing about what happens when the
review goes the other way. There was no way to record it: ``IRStatus`` held ``draft | locked |
stale | superseded``, ``POST /irs/{id}/lock`` had no counterpart, and the review surface offered one
button.

A refusal left as ``draft`` is indistinguishable from a draft nobody has opened, so it returns to
the next reviewer's queue forever. That is decision **6**'s own argument — *"non-obligation clauses
are marked reviewed, not skipped… if they are simply absent, '50 IRs from 200 clauses' is
uninterpretable"* — one level up, about the IR rather than the clause.

Found the way these things are found: an operator mis-clicked 확정 on an IR extracted from
21 CFR 700.3(g), a paragraph of the Definitions section that states no obligation, and there was
neither a way to undo it nor anywhere to record that it had been refused.

``IR_VISIBLE_STATUSES`` is unchanged and stays ``(LOCKED,)``, so nothing downstream reads the new
state: a rejected IR is inert exactly as a draft is. What changes is that it is inert *and*
accounted for.

Fresh-DB safe: the baseline builds from the models via ``create_all``, so the type already carries
the new label and the columns already exist there. ``ADD VALUE IF NOT EXISTS`` and
``ADD COLUMN IF NOT EXISTS`` make both halves no-ops.

Note the enum value is added outside a transaction block. ``ALTER TYPE … ADD VALUE`` cannot run
inside one before PostgreSQL 12, and Alembic wraps migrations in a transaction; ``COMMIT`` first is
the documented way through, and it is safe here because the statement is idempotent.

Revision ID: 0012
Revises: 0011
"""

from __future__ import annotations

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

REASONS = (
    "not_an_obligation",
    "misread_clause",
    "not_atomic",
    "wrong_citation",
    "duplicate",
)


def upgrade() -> None:
    op.execute("COMMIT")
    op.execute("ALTER TYPE ir_status ADD VALUE IF NOT EXISTS 'rejected'")

    values = ", ".join(f"'{reason}'" for reason in REASONS)
    op.execute(
        f"DO $$ BEGIN "
        f"IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'rejection_reason') THEN "
        f"CREATE TYPE rejection_reason AS ENUM ({values}); "
        f"END IF; END $$;"
    )
    op.execute("ALTER TABLE irs ADD COLUMN IF NOT EXISTS rejected_by uuid")
    op.execute("ALTER TABLE irs ADD COLUMN IF NOT EXISTS rejected_at timestamp with time zone")
    op.execute("ALTER TABLE irs ADD COLUMN IF NOT EXISTS rejection_reason rejection_reason")
    op.execute("ALTER TABLE irs ADD COLUMN IF NOT EXISTS rejection_note text")


def downgrade() -> None:
    op.execute("ALTER TABLE irs DROP COLUMN IF EXISTS rejection_note")
    op.execute("ALTER TABLE irs DROP COLUMN IF EXISTS rejection_reason")
    op.execute("ALTER TABLE irs DROP COLUMN IF EXISTS rejected_at")
    op.execute("ALTER TABLE irs DROP COLUMN IF EXISTS rejected_by")
    op.execute("DROP TYPE IF EXISTS rejection_reason")
    # `ir_status` keeps its 'rejected' label: PostgreSQL cannot drop an enum value, and a row may
    # already carry it. Leaving it is the only option that does not lose a review decision.
