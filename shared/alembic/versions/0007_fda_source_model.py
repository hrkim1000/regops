"""Two enum values the FDA source model needs — ``doc_type.regulation`` and
``exclusion_reason.non_binding``.

Authorised by [ADR-0018](../../../docs/design/ADR-0018-fda-source-model.md), which deliberately did
*not* make them: the ADR records the decision and the build slice carries the schema change, so the
commit that settles a question stays separable from the commit that acts on it.

**``doc_type.regulation``** (ADR-0018 decision 3). A CFR Part is a codified agency rule issued
directly under a statute. ``enforcement_rule`` was the tempting reuse and is wrong: ``law`` /
``decree`` / ``enforcement_rule`` name rungs of the Korean statutory ladder (법률 → 시행령 →
시행규칙), and a CFR Part has no 시행령 tier above it — mapping onto it would assert a hierarchy
that does not exist and would make the value mean two different things depending on the authority.
The parser profile keys on the ``doc_type`` value, **never on the cell**, so a domain-neutral value
is what keeps ADR-0002 decision 3 honest.

**``exclusion_reason.non_binding``** (ADR-0018 decision 9). FDA guidance is explicitly nonbinding and
the English modal inventory has no ``should``, so extraction over it yields zero IRs — the correct
result, which reads as a coverage hole unless it is stated as a rule. Guidance is therefore skipped
by ``doc_type`` and every clause is written excluded for this reason: examined-and-excluded, never
unexamined. It is distinct from ``permissive``, which is about a modal *inside* a binding instrument;
here the instrument itself binds nobody.

No table, column, index or constraint changes — adding a label to an existing enum touches no row.

Fresh-DB note: the baseline builds the schema with ``create_all`` from the models, and both values
are now in the ``StrEnum``s, so a fresh database already has them. ``ADD VALUE IF NOT EXISTS`` makes
this a no-op there and applies cleanly to a live one — the same idiom 0003 uses for ``drift_signal``.

PostgreSQL note: since 12, ``ALTER TYPE … ADD VALUE`` runs inside a transaction block, which is how
Alembic executes migrations here. What is still forbidden is *using* the new label in the same
transaction, and nothing below does — no row is written or cast.

Downgrade is a no-op **on purpose**: PostgreSQL cannot remove a value from an enum. Dropping and
recreating the type would require rewriting every column that uses it, and ``doc_type`` is on
``documents`` — evidence. A downgrade that silently rewrote the corpus to reverse a two-label
addition would be far more destructive than the thing it undoes.

Revision ID: 0007
Revises: 0006
"""

from __future__ import annotations

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

#: Enum → labels this migration appends. Order matters only for readability; PostgreSQL appends.
NEW_ENUM_VALUES: dict[str, tuple[str, ...]] = {
    "doc_type": ("regulation",),
    "exclusion_reason": ("non_binding",),
}


def upgrade() -> None:
    for enum_name, values in NEW_ENUM_VALUES.items():
        for value in values:
            op.execute(f"ALTER TYPE {enum_name} ADD VALUE IF NOT EXISTS '{value}';")


def downgrade() -> None:
    """Intentionally empty — see the module docstring. PostgreSQL cannot drop an enum label."""
