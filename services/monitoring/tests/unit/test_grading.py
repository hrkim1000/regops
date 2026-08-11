"""Impact grading and the wording it justifies — the pure half of phase 1.4.

Grading has three inputs and a fixed precedence, and the precedence is the part worth pinning: a
human-locked obligation resting on text that has moved outranks any volume of unreviewed churn,
because it is the only input here that carries a person's assertion.
"""

from __future__ import annotations

from app.grade import (
    BASIS_BULK_CHANGE,
    BASIS_CLAUSE_REMOVED,
    BASIS_LOCKED_IR,
    BASIS_ROUTINE,
    CELL_SCOPE_NOTICE,
    SUMMARY_PATH_LIMIT,
    Grade,
    compose_summary,
    compose_title,
    grade,
)
from regops_shared.constants import ALERT_BULK_CLAUSE_COUNT, AlertSeverity, ChangeKind


def test_a_locked_ir_over_moved_evidence_is_the_top_grade() -> None:
    result = grade(change_kinds={ChangeKind.MODIFIED.value}, clause_count=1, locked_ir_count=2)

    assert result.severity is AlertSeverity.HIGH
    assert result.basis == BASIS_LOCKED_IR
    assert result.locked_ir_count == 2


def test_a_locked_ir_outranks_a_removal_and_a_bulk_change() -> None:
    """Precedence, not addition. One person's assertion beats a hundred unreviewed edits."""
    result = grade(
        change_kinds={ChangeKind.REMOVED.value},
        clause_count=ALERT_BULK_CLAUSE_COUNT * 5,
        locked_ir_count=1,
    )

    assert (result.severity, result.basis) == (AlertSeverity.HIGH, BASIS_LOCKED_IR)


def test_a_removal_is_medium_even_with_nothing_extracted_from_it() -> None:
    """ "This provision no longer exists" is the highest-impact thing an amendment can say."""
    result = grade(change_kinds={ChangeKind.REMOVED.value}, clause_count=1, locked_ir_count=0)

    assert (result.severity, result.basis) == (AlertSeverity.MEDIUM, BASIS_CLAUSE_REMOVED)


def test_size_alone_reaches_medium_at_the_threshold() -> None:
    below = grade(
        change_kinds={ChangeKind.MODIFIED.value},
        clause_count=ALERT_BULK_CLAUSE_COUNT - 1,
        locked_ir_count=0,
    )
    at = grade(
        change_kinds={ChangeKind.MODIFIED.value},
        clause_count=ALERT_BULK_CLAUSE_COUNT,
        locked_ir_count=0,
    )

    assert (below.severity, below.basis) == (AlertSeverity.LOW, BASIS_ROUTINE)
    assert (at.severity, at.basis) == (AlertSeverity.MEDIUM, BASIS_BULK_CHANGE)


def test_a_routine_amendment_is_low() -> None:
    result = grade(
        change_kinds={ChangeKind.MODIFIED.value, ChangeKind.ADDED.value},
        clause_count=3,
        locked_ir_count=0,
    )

    assert (result.severity, result.basis) == (AlertSeverity.LOW, BASIS_ROUTINE)


# --- composition --------------------------------------------------------------------------------


def _summary(**overrides) -> str:
    kwargs = {
        "document_title": "화장품법",
        "version_label": "MST 282015",
        "effective_date_iso": "2026-04-02",
        "grade_result": Grade(AlertSeverity.LOW, BASIS_ROUTINE),
        "kind_counts": {ChangeKind.MODIFIED.value: 2},
        "clause_paths": ["제5조", "제6조"],
    }
    kwargs.update(overrides)
    return compose_summary(**kwargs)


def test_every_summary_states_the_cell_level_limitation() -> None:
    """ADR-0009 decision 5. Phase 1 can only say "something in your cell changed", so it says it —
    in the alert, not in a footnote nobody opens."""
    assert CELL_SCOPE_NOTICE in _summary()


def test_the_summary_names_the_version_and_the_effective_date() -> None:
    body = _summary()

    assert "MST 282015" in body
    assert "시행일 2026-04-02 기준" in body


def test_a_long_clause_list_is_truncated_with_a_remainder() -> None:
    """A summary is a subject line. Forty addresses is a wall, and the full list is on the alert."""
    paths = [f"제{n}조" for n in range(1, 41)]

    body = _summary(clause_paths=paths, kind_counts={ChangeKind.MODIFIED.value: 40})

    assert "제1조" in body
    assert f"외 {40 - SUMMARY_PATH_LIMIT}건" in body
    assert "제40조" not in body


def test_the_locked_ir_notice_names_how_many() -> None:
    body = _summary(grade_result=Grade(AlertSeverity.HIGH, BASIS_LOCKED_IR, 3))

    assert "확정(lock)된 요구사항 3건" in body


def test_the_title_carries_the_document_and_the_count() -> None:
    assert compose_title(document_title="화장품법", clause_count=12) == "화장품법 — 조문 12건 변경"
