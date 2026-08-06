"""The clause read serializer.

One property is worth a test rather than a review: a ``table`` clause's ordered header must survive
serialization **as a list**. It is the only place the column order exists — a ``table_row``'s
``row_columns`` is a ``jsonb`` object whose keys Postgres sorts — so a serializer that normalized it
to a mapping would leave every annex limit table renderable only in alphabetical column order, and
the resulting table would look correct while stating the wrong limits (ADR-0014 decision 4).
"""

from __future__ import annotations

import uuid
from datetime import date

from app.api.v1.clauses import _clause_out
from app.models import Clause
from regops_shared.constants import ClauseKind

HEADER = ["원료명", "사용한도", "CAS No.", "비고"]


def _clause(**overrides) -> Clause:
    clause = Clause(
        document_version_id=uuid.uuid4(),
        clause_path="별표2/표1/행1",
        path_segments=["별표2", "표1", "행1"],
        level=3,
        ordinal=7,
        kind=ClauseKind.TABLE_ROW,
        heading=None,
        text="",
        row_columns=None,
        parent_clause_id=None,
        source_ref=None,
        authority_changed=None,
        effective_date=None,
        effective_date_phrase=None,
    )
    clause.id = uuid.uuid4()
    for key, value in overrides.items():
        setattr(clause, key, value)
    return clause


def test_table_header_stays_ordered() -> None:
    out = _clause_out(_clause(kind=ClauseKind.TABLE, clause_path="별표2/표1", row_columns=HEADER))

    assert out["row_columns"] == HEADER, "the ordered header is the only record of column order"


def test_table_row_carries_its_cells_and_its_own_address() -> None:
    cells = {"원료명": "글루타랄(펜탄-1,5-디알)", "사용한도": "0.1%"}
    out = _clause_out(_clause(row_columns=cells))

    # An annex table row is a Clause and is cited exactly like a 조 (ADR-0014).
    assert out["clause_path"] == "별표2/표1/행1"
    assert out["path_segments"] == ["별표2", "표1", "행1"]
    assert out["row_columns"] == cells


def test_unresolvable_clause_date_renders_as_its_phrase_not_a_date() -> None:
    """ADR-0013 — a date that cannot be resolved stays null and the raw 부칙 phrase is kept."""
    out = _clause_out(
        _clause(effective_date=None, effective_date_phrase="공포 후 6개월이 경과한 날부터 시행")
    )

    assert out["effective_date"] is None
    assert out["effective_date_phrase"] == "공포 후 6개월이 경과한 날부터 시행"


def test_clause_date_is_serialized_as_an_iso_day() -> None:
    out = _clause_out(_clause(effective_date=date(2026, 12, 31)))

    assert out["effective_date"] == "2026-12-31"
