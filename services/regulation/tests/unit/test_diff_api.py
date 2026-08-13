"""The clause-diff read serializer — what the monitoring dashboard renders a change from.

Two properties are worth a test rather than a review, and both are about *not misleading a reader*:

- **A renumber carries both addresses.** ``from_clause_path`` is what lets a UI say 제7조 → 제9조
  instead of showing a removal beside an unrelated addition. That distinction is ADR-0002 decision 7
  as a reader experiences it, and a serializer that dropped the old path would undo it in the last
  step.
- **Truncated clause text is flagged as truncated.** A 별표 clause in the gated corpus runs to
  340 KB, so the response has to bound it — but a shortened clause shown as if whole is worse than
  no clause at all, because the reader draws a conclusion from text that was cut away.
"""

from __future__ import annotations

import uuid

from app.api.v1.diffs import DIFF_TEXT_MAX_CHARS, _diff_out, _side
from app.models import Clause, ClauseDiff
from regops_shared.constants import ChangeKind, ClauseKind


def _clause(*, path: str, text: str, ordinal: int = 1) -> Clause:
    clause = Clause(
        document_version_id=uuid.uuid4(),
        clause_path=path,
        path_segments=path.split("/"),
        level=len(path.split("/")),
        ordinal=ordinal,
        kind=ClauseKind.PROSE,
        heading=None,
        text=text,
        content_hash="0" * 64,
    )
    clause.id = uuid.uuid4()
    return clause


def _diff(**overrides) -> ClauseDiff:
    diff = ClauseDiff(
        from_version_id=uuid.uuid4(),
        to_version_id=uuid.uuid4(),
        clause_path="제5조",
        change_kind=ChangeKind.MODIFIED,
    )
    diff.id = uuid.uuid4()
    for key, value in overrides.items():
        setattr(diff, key, value)
    return diff


def test_a_modification_carries_both_sides_of_the_text() -> None:
    """ "What actually changed" is the whole question an alert sends a reader here to answer."""
    before = _clause(path="제5조", text="기록을 3년간 보관하여야 한다.")
    after = _clause(path="제5조", text="기록을 5년간 보관하여야 한다.")
    diff = _diff(from_clause_id=before.id, to_clause_id=after.id, match_basis="path")

    payload = _diff_out(diff, {before.id: before, after.id: after})

    assert payload["from"]["text"] == "기록을 3년간 보관하여야 한다."
    assert payload["to"]["text"] == "기록을 5년간 보관하여야 한다."
    assert payload["change_kind"] == ChangeKind.MODIFIED.value


def test_a_renumber_names_both_addresses_so_it_can_render_as_a_move() -> None:
    """ADR-0002 decision 7, at the last step: delete + add is two false alerts, not one move."""
    before = _clause(path="제7조", text="동일한 본문")
    after = _clause(path="제9조", text="동일한 본문")
    diff = _diff(
        clause_path="제9조",
        from_clause_path="제7조",
        change_kind=ChangeKind.RENUMBERED,
        from_clause_id=before.id,
        to_clause_id=after.id,
        match_basis="authority",
    )

    payload = _diff_out(diff, {before.id: before, after.id: after})

    assert (payload["from_clause_path"], payload["clause_path"]) == ("제7조", "제9조")
    assert payload["change_kind"] == ChangeKind.RENUMBERED.value
    assert payload["match_basis"] == "authority"
    # Stated by the authority, so nothing was inferred and there is no similarity to report.
    assert payload["similarity"] is None


def test_a_removal_has_no_new_side_and_an_addition_has_no_old_one() -> None:
    before = _clause(path="제8조", text="삭제될 본문")
    removal = _diff(clause_path="제8조", change_kind=ChangeKind.REMOVED, from_clause_id=before.id)

    payload = _diff_out(removal, {before.id: before})

    assert payload["to"] is None
    assert payload["from"]["clause_path"] == "제8조"


def test_an_inferred_pairing_reports_its_confidence_and_its_review_flag() -> None:
    """A stated move and a guessed one must not render alike — one is a claim nobody checked."""
    before = _clause(path="제7조", text="비슷한 본문 A")
    after = _clause(path="제9조", text="비슷한 본문 B")
    diff = _diff(
        clause_path="제9조",
        from_clause_path="제7조",
        change_kind=ChangeKind.RENUMBERED,
        from_clause_id=before.id,
        to_clause_id=after.id,
        similarity=0.72,
        match_basis="similarity",
        needs_review=True,
    )

    payload = _diff_out(diff, {before.id: before, after.id: after})

    assert payload["similarity"] == 0.72
    assert payload["match_basis"] == "similarity"
    assert payload["needs_review"] is True


def test_a_long_clause_is_truncated_and_says_so() -> None:
    """별표 1 holds single clauses of 340 KB. Shortened silently, it would be read as complete."""
    huge = _clause(path="별표1", text="가" * (DIFF_TEXT_MAX_CHARS + 500))

    side = _side(huge)

    assert len(side["text"]) == DIFF_TEXT_MAX_CHARS
    assert side["truncated"] is True


def test_a_short_clause_is_not_flagged_as_truncated() -> None:
    side = _side(_clause(path="제5조", text="짧은 본문"))

    assert side["truncated"] is False
