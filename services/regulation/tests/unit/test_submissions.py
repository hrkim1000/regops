"""Submission-requirement derivation — and above all, what it refuses to claim.

The precision of this feature *is* its regexes, so the counter-examples matter more than the happy
path. Every negative case below is real text from the archived corpus that an earlier, looser
pattern matched wrongly:

- ``다음 각 호의 **어느 하나**에 해당하는 의료기기`` — enumerates products, not documents
- ``다음 각 호의 **사항**과 관련된 자료의 제출`` — enumerates matters, not documents
- ``제1항의 일부 자료를 **제출하지 아니할 수 있다**`` — an *exemption*; reading it as a requirement
  inverts the clause, which is the worst failure this module could have

The other half is the invariant the whole design rests on: **a condition is never flattened.** A
list rendered as a settled checklist when 40% of these procedures are conditional would manufacture
exactly the compliance error the gap-analysis pillar exists to find.
"""

from __future__ import annotations

import uuid

import pytest

from app.submissions import Caveat, derive
from app.submissions import _is_submission_clause as is_submission_clause
from regops_shared.constants import ClauseKind


class FakeClause:
    """Stands in for a `Clause` row. The derivation reads attributes, never the session."""

    def __init__(self, path, text, *, kind=ClauseKind.PROSE, parent=None, ordinal=0, heading=None):
        self.id = uuid.uuid4()
        self.clause_path = path
        self.text = text
        self.kind = kind
        self.parent_clause_id = parent
        self.ordinal = ordinal
        self.heading = heading


class FakeSession:
    def __init__(self, clauses):
        self._clauses = clauses

    def scalars(self, _stmt):
        return self._clauses


def run(clauses):
    return derive(FakeSession(clauses), uuid.uuid4())


# --- detection ---------------------------------------------------------------------------------

REAL = (
    "① 제3조제1항에 해당하는 사람이 적합성인정등 심사를 받고자 하는 경우에는 "
    "별지 제1호서식의 신청서에 다음 각 호의 자료를 첨부하여 "
    "품질관리심사기관의 장에게 제출하여야 한다."
)


def test_a_real_submission_clause_is_detected() -> None:
    assert is_submission_clause(FakeClause("제7조/제1항", REAL))


@pytest.mark.parametrize(
    ("label", "text"),
    [
        (
            "enumerates products",
            "⑫ 다음 각 호의 어느 하나에 해당하는 의료기기를 제조하는 제조소에 대하여 "
            "우선심사를 신청하는 자는 자료를 제출하여야 한다.",
        ),
        (
            "enumerates matters",
            "③ 식품의약품안전처장은 관계 기관의 장에게 다음 각 호의 사항과 관련된 자료의 제출 "
            "또는 정보의 제공 등 필요한 협조를 요청할 수 있다.",
        ),
        (
            "no enumeration",
            "② 신청인은 별지 제3호서식의 신청서에 관련 자료를 첨부하여 제출하여야 한다.",
        ),
        (
            "no document noun",
            "② 제조업자는 다음 각 호의 기준을 갖추어 관리하여야 한다.",
        ),
    ],
)
def test_clauses_that_are_not_document_lists_are_refused(label: str, text: str) -> None:
    assert not is_submission_clause(FakeClause("제N조/제1항", text)), label


def test_an_exemption_is_never_read_as_a_requirement() -> None:
    """The inversion failure. "제출하지 아니할 수 있다" says what may be *omitted*."""
    text = (
        "② 제1항에도 불구하고 다음 각 호에 해당하는 경우에는 제1항의 일부 자료를 "
        "제출하지 아니할 수 있다."
    )
    assert not is_submission_clause(FakeClause("제3조/제2항", text))


def test_non_prose_clauses_are_skipped() -> None:
    """A form or a table row is not a procedure, whatever words its layout happens to contain."""
    assert not is_submission_clause(FakeClause("별지1", REAL, kind=ClauseKind.FORM))
    assert not is_submission_clause(FakeClause("별표2/표1/행1", REAL, kind=ClauseKind.TABLE_ROW))


# --- the derived shape -------------------------------------------------------------------------


def _procedure_with_items():
    parent = FakeClause("제7조/제1항", REAL, ordinal=0, heading="심사의 신청")
    items = [
        FakeClause(
            "제7조/제1항/제1호", "1. 의료기기 제조업 허가증 사본", parent=parent.id, ordinal=1
        ),
        FakeClause(
            "제7조/제1항/제2호", "2. 다음 각 목에 해당되는 자료", parent=parent.id, ordinal=2
        ),
        FakeClause(
            "제7조/제1항/제3호",
            "3. 제2호에도 불구하고, 정기심사를 받을 경우 제2호를 제외한 자료",
            parent=parent.id,
            ordinal=3,
        ),
        FakeClause(
            "제7조/제1항/제4호",
            "4. 그 밖에 심사에 필요한 자료로서 총리령으로 정하는 자료",
            parent=parent.id,
            ordinal=4,
        ),
    ]
    return [parent, *items]


def test_every_item_arrives_with_its_own_citation() -> None:
    """The answer is citation-native: the item *is* a clause, so evidence is not bolted on."""
    [requirement] = run(_procedure_with_items())

    assert requirement.clause_path == "제7조/제1항"
    assert [d.clause_path for d in requirement.documents] == [
        "제7조/제1항/제1호",
        "제7조/제1항/제2호",
        "제7조/제1항/제3호",
        "제7조/제1항/제4호",
    ]
    assert all(d.text for d in requirement.documents), "item text is the document name, verbatim"


def test_the_form_reference_is_verbatim_and_unresolved() -> None:
    """Resolving a cross-reference is phase 2.1. A guessed link is unverified evidence."""
    [requirement] = run(_procedure_with_items())
    assert requirement.form_reference == "별지 제1호서식"


def test_the_recipient_is_captured_without_swallowing_the_sentence() -> None:
    [requirement] = run(_procedure_with_items())
    assert requirement.recipient == "품질관리심사기관의 장"


def test_alternative_recipients_are_kept_together() -> None:
    """ "A 또는 B에게" is one destination with two options, not two phrases.

    `또는` ends in 는 like a topic marker, so a naive boundary rule drops the first alternative —
    observed live on 의료기기법 시행규칙 제9조제3항, which named only 기술문서심사기관의 장.
    """
    parent = FakeClause(
        "제9조/제3항",
        "③ 심사를 받으려는 자는 다음 각 호의 자료를 첨부하여 "
        "식품의약품안전처장 또는 기술문서심사기관의 장에게 제출하여야 한다.",
    )
    item = FakeClause("제9조/제3항/제1호", "1. 개발경위에 관한 자료", parent=parent.id, ordinal=1)
    [requirement] = run([parent, item])

    assert requirement.recipient == "식품의약품안전처장 또는 기술문서심사기관의 장"


# --- the invariant: conditions are never flattened ---------------------------------------------


def test_a_conditional_item_is_flagged_and_keeps_its_condition_verbatim() -> None:
    [requirement] = run(_procedure_with_items())
    conditional = requirement.documents[2]

    assert conditional.conditional
    assert "제2호에도 불구하고" in (conditional.condition_text or conditional.text)


def test_an_unconditional_item_carries_no_condition() -> None:
    """The flag has to discriminate — if everything is conditional, nothing is."""
    [requirement] = run(_procedure_with_items())
    assert not requirement.documents[0].conditional
    assert requirement.documents[0].condition_text is None


def test_a_wholly_conditional_item_is_flagged_without_duplicating_its_text() -> None:
    """`condition_text is None` must never be read as "unconditional".

    Most real items are one conditional sentence end to end — "소재지 변경의 경우: …서류". Echoing
    the whole item back as its own condition would double the payload and tell a reader nothing, so
    the boolean carries it and the phrase stays null.
    """
    parent = FakeClause(
        "제5조/제2항",
        "② 변경등록을 하려는 자는 다음 각 호의 서류를 첨부하여 제출하여야 한다.",
    )
    item = FakeClause(
        "제5조/제2항/제2호",
        "2. 제조소의 소재지 변경의 경우: 제3조제2항제3호에 해당하는 서류",
        parent=parent.id,
        ordinal=1,
    )
    [requirement] = run([parent, item])
    [document] = requirement.documents

    assert document.conditional, "the item plainly applies only in one case"
    assert document.condition_text is None, "the condition is the whole item; do not repeat it"
    assert Caveat.CONDITIONAL_ITEMS in requirement.caveats


def test_delegation_and_nesting_are_flagged_per_item() -> None:
    [requirement] = run(_procedure_with_items())

    assert requirement.documents[1].has_sub_items, "다음 각 목 — the detail is one level down"
    assert requirement.documents[3].delegates, "총리령으로 정하는 — content lives elsewhere"


def test_the_requirement_publishes_machine_readable_caveats() -> None:
    """A caveat expressed only in prose is one a UI silently drops."""
    [requirement] = run(_procedure_with_items())

    assert Caveat.CONDITIONAL_PROCEDURE in requirement.caveats  # "…경우에는" on the 항
    assert Caveat.CONDITIONAL_ITEMS in requirement.caveats
    assert Caveat.NESTED_ITEMS in requirement.caveats
    assert Caveat.DELEGATED_ITEMS in requirement.caveats
    assert not requirement.is_definitive


def test_a_plain_unconditional_procedure_is_definitive() -> None:
    """The negative case for `is_definitive` — otherwise the flag means nothing."""
    parent = FakeClause(
        "제5조/제1항",
        "① 신고인은 별지 제2호서식의 신고서에 다음 각 호의 서류를 첨부하여 제출하여야 한다.",
    )
    items = [
        FakeClause("제5조/제1항/제1호", "1. 사업자등록증 사본", parent=parent.id, ordinal=1),
        FakeClause("제5조/제1항/제2호", "2. 시설 명세서", parent=parent.id, ordinal=2),
    ]
    [requirement] = run([parent, *items])

    assert requirement.caveats == ()
    assert requirement.is_definitive


def test_an_unparsed_item_list_is_a_caveat_not_an_empty_list() -> None:
    """An empty `documents` with no caveat would read as "nothing is required"."""
    parent = FakeClause(
        "제9조/제1항",
        "① 신청인은 다음 각 호의 서류를 첨부하여 제출하여야 한다. 1. 신청서 2. 명세서",
    )
    [requirement] = run([parent])

    assert requirement.documents == []
    assert Caveat.NO_ITEMS_PARSED in requirement.caveats
    assert not requirement.is_definitive


def test_a_cross_instrument_reference_is_flagged() -> None:
    """법 제8조제3항 → 시행규칙: the list read from one instrument alone may be incomplete."""
    parent = FakeClause(
        "제18조/제2항",
        "② 법 제8조제3항에 따라 변경승인을 받으려는 자는 별지 제16호서식의 신청서에 "
        "다음 각 호의 서류를 첨부하여 식품의약품안전처장에게 제출해야 한다.",
    )
    item = FakeClause("제18조/제2항/제1호", "1. 변경계획서", parent=parent.id, ordinal=1)
    [requirement] = run([parent, item])

    assert Caveat.CROSS_INSTRUMENT in requirement.caveats


def test_procedures_come_back_in_document_order() -> None:
    first = FakeClause("제5조/제1항", REAL, ordinal=0)
    later = FakeClause("제9조/제1항", REAL, ordinal=10)
    assert [r.clause_path for r in run([first, later])] == ["제5조/제1항", "제9조/제1항"]
