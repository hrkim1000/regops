"""``doc_type.codified_statute`` — the FD&C Act, and every statute that reaches us as a code.

Authorised by [ADR-0018](../../../docs/design/ADR-0018-fda-source-model.md) decision 12, which
settles that the FD&C Act is ingested as 21 U.S.C. chapter 9 from govinfo. The ADR did not make the
schema change, on the same separation 0007 followed: the commit that records a decision stays apart
from the commit that acts on it.

**Why not ``law``.** The tempting reuse, and wrong for the same reason ``enforcement_rule`` was
wrong for a CFR Part in 0007. ``law`` names 법률, a rung of the Korean statutory ladder, and it
routes to the ``law_structured`` profile — which reads 조/항/호/목 as XML *elements*. A govinfo USC
granule is HTML that is not even well-formed XML; it fails ``defusedxml`` on its first character
reference, so routing the Act through ``law`` would fail at the envelope before reaching a single
provision. The two are different **shapes**, and ``doc_type`` is what parser selection keys on
(ADR-0002 decision 3) — so a value that means "a statute as codified into a subject-arranged code"
is what keeps that selection free of any branch on authority.

The name is deliberately not ``statute``: what is ingested is the Office of the Law Revision
Counsel's *codification*, republished annually, and not the enacted act itself. ``PLAW`` carries
enactments and is not built (ADR-0018 decision 12), so the distinction the name draws is real and
the gate consequence follows from it — the statute cannot meet the ≤24h detection gate.

No table, column, index or constraint changes — adding a label to an existing enum touches no row.

Fresh-DB note: the baseline builds the schema with ``create_all`` from the models and the value is
now in the ``StrEnum``, so a fresh database already has it. ``ADD VALUE IF NOT EXISTS`` makes this a
no-op there and applies cleanly to a live one.

PostgreSQL note: since 12, ``ALTER TYPE … ADD VALUE`` runs inside a transaction block, which is how
Alembic executes migrations here. What is still forbidden is *using* the new label in the same
transaction, and nothing below does — no row is written or cast.

Downgrade is a no-op **on purpose**: PostgreSQL cannot remove a value from an enum, and ``doc_type``
sits on ``documents``, which is evidence. See 0007.

Revision ID: 0009
Revises: 0008
"""

from __future__ import annotations

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

#: Enum → labels this migration appends.
NEW_ENUM_VALUES: dict[str, tuple[str, ...]] = {
    "doc_type": ("codified_statute",),
}


def upgrade() -> None:
    for enum_name, values in NEW_ENUM_VALUES.items():
        for value in values:
            op.execute(f"ALTER TYPE {enum_name} ADD VALUE IF NOT EXISTS '{value}';")


def downgrade() -> None:
    """Intentionally empty — see the module docstring. PostgreSQL cannot drop an enum label."""
