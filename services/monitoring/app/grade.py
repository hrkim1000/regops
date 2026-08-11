"""Impact grading, and the wording that has to be honest about what it can and cannot say.

Three inputs, fixed by the phase plan: ``change_kind``, the substantive clause count, and whether a
locked IR cites the touched clause. Grading writes onto ``alerts`` rather than into a table of its
own (ADR-0009 decision 3), so this module is pure — it decides a severity and composes the text that
justifies it, and :mod:`app.routing` is what persists either.

**Phase 1 routes on cell, not on product** (ADR-0007; ADR-0009 decision 5). An IR applies to a cell
until the Product context exists, so the strongest true statement an alert can make is *"something
in your cell changed, and this much of it"*. The summary says that outright. Implying product-level
precision would be the more useful-sounding claim and the one the data cannot support, and a
customer who learns that the hard way stops trusting the alerts that were right.

The thresholds are deliberately crude and phase 1.6 re-derives them from pilot data. What is *not*
provisional is the ordering: a human-locked obligation resting on text that has moved outranks any
amount of unreviewed churn, because it is the only input here that carries a person's assertion.
"""

from __future__ import annotations

from dataclasses import dataclass

from regops_shared.constants import (
    ALERT_BULK_CLAUSE_COUNT,
    AlertSeverity,
    ChangeKind,
)

#: Why an alert got the grade it did. A closed inventory rather than prose: the pilot has to be able
#: to count "how many of our high-severity alerts were high because of a locked IR" without parsing
#: a sentence, and the false-positive rate is watched per basis even though no gate measures it.
BASIS_LOCKED_IR = "locked_ir"
BASIS_CLAUSE_REMOVED = "clause_removed"
BASIS_BULK_CHANGE = "bulk_change"
BASIS_ROUTINE = "routine"


@dataclass(frozen=True, slots=True)
class Grade:
    severity: AlertSeverity
    basis: str
    locked_ir_count: int = 0


def grade(
    *,
    change_kinds: set[str],
    clause_count: int,
    locked_ir_count: int,
) -> Grade:
    """Grade one amendment for one cell.

    ``change_kinds`` and ``clause_count`` cover **substantive** changes only — renumbers and moves
    are dropped before they reach here, so a pure renumbering never gets graded at all.
    """
    if locked_ir_count > 0:
        # A person locked this obligation, and the text it rests on has moved. Nothing else this
        # phase can measure carries a human assertion.
        return Grade(AlertSeverity.HIGH, BASIS_LOCKED_IR, locked_ir_count)
    if ChangeKind.REMOVED.value in change_kinds:
        # "This provision no longer exists" is the highest-impact thing an amendment can say, even
        # where nobody had extracted an obligation from it yet.
        return Grade(AlertSeverity.MEDIUM, BASIS_CLAUSE_REMOVED, 0)
    if clause_count >= ALERT_BULK_CLAUSE_COUNT:
        return Grade(AlertSeverity.MEDIUM, BASIS_BULK_CHANGE, 0)
    return Grade(AlertSeverity.LOW, BASIS_ROUTINE, 0)


# --- composition ------------------------------------------------------------------------------
#
# User-facing wording is Korean, matching `assistant`'s answer text: the document titles, the clause
# paths and the audience are all Korean, and an English frame around 제5조제2항 helps nobody.

_KIND_LABEL: dict[str, str] = {
    ChangeKind.ADDED.value: "신설",
    ChangeKind.REMOVED.value: "삭제",
    ChangeKind.MODIFIED.value: "개정",
    ChangeKind.RENUMBERED.value: "조번호 변경",
    ChangeKind.MOVED.value: "위치 이동",
}

#: Clause paths named in the summary before it says "외 N건". A summary is a subject line, and one
#: listing forty addresses is a wall nobody reads — the full list is on the alert.
SUMMARY_PATH_LIMIT = 5

#: The Phase 1 limitation, stated in the alert rather than in a footnote nobody opens.
CELL_SCOPE_NOTICE = (
    "이 알림은 셀(규제기관 × 제품군) 단위입니다. "
    "개별 제품에 대한 영향 여부는 아직 판단하지 않습니다."
)

_BASIS_NOTICE: dict[str, str] = {
    BASIS_LOCKED_IR: "확정(lock)된 요구사항이 근거로 삼던 조문이 변경되었습니다.",
    BASIS_CLAUSE_REMOVED: "삭제된 조문이 포함되어 있습니다.",
    BASIS_BULK_CHANGE: "변경된 조문 수가 많습니다.",
    BASIS_ROUTINE: "일반 개정입니다.",
}


def compose_title(*, document_title: str, clause_count: int) -> str:
    return f"{document_title} — 조문 {clause_count}건 변경"


def compose_summary(
    *,
    document_title: str,
    version_label: str | None,
    effective_date_iso: str | None,
    grade_result: Grade,
    kind_counts: dict[str, int],
    clause_paths: list[str],
) -> str:
    """The alert body: what changed, on what evidence, and what this alert does not claim."""
    lines = [f"{document_title}" + (f" ({version_label})" if version_label else "")]
    if effective_date_iso:
        lines.append(f"시행일 {effective_date_iso} 기준")

    breakdown = ", ".join(
        f"{_KIND_LABEL.get(kind, kind)} {count}건"
        for kind, count in sorted(kind_counts.items(), key=lambda item: (-item[1], item[0]))
    )
    if breakdown:
        lines.append(breakdown)

    shown = clause_paths[:SUMMARY_PATH_LIMIT]
    if shown:
        listing = ", ".join(shown)
        remainder = len(clause_paths) - len(shown)
        lines.append(listing + (f" 외 {remainder}건" if remainder > 0 else ""))

    notice = _BASIS_NOTICE.get(grade_result.basis)
    if notice:
        if grade_result.basis == BASIS_LOCKED_IR:
            notice = (
                f"확정(lock)된 요구사항 {grade_result.locked_ir_count}건의 "
                "근거 조문이 변경되었습니다."
            )
        lines.append(notice)

    lines.append(CELL_SCOPE_NOTICE)
    return "\n".join(lines)


__all__ = [
    "BASIS_BULK_CHANGE",
    "BASIS_CLAUSE_REMOVED",
    "BASIS_LOCKED_IR",
    "BASIS_ROUTINE",
    "CELL_SCOPE_NOTICE",
    "Grade",
    "compose_summary",
    "compose_title",
    "grade",
]
