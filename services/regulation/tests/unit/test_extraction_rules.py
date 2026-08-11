"""The atomicity rule, as tests rather than as prose (ADR-0004 decision 1).

Every row of the ADR's worked-example table is a case here. That table is the whole reason IR counts
are comparable between people and between runs, so it is the part that must fail loudly if someone
loosens the modal inventory or the triage order.

No LLM is reached in this file: everything under test is the deterministic half of the agent
(:mod:`app.extraction.rules`), which is precisely what makes the rule operative — "does this clause
contain an obligation modal" is a regex question, never a judgement call.
"""

from __future__ import annotations

import pytest

from app.extraction.rules import (
    found_modals,
    has_permissive,
    rule_set_for,
    triage,
)
from regops_shared.constants import (
    MODAL_INVENTORY,
    TAXONOMY_CODES,
    ClassificationKind,
    ClauseKind,
    Domain,
    ExclusionReason,
)

SAMD = rule_set_for(Domain.SAMD, "ko")
COSMETIC = rule_set_for(Domain.COSMETIC, "ko")
EN = rule_set_for(Domain.SAMD, "en")


def _triage(text: str, *, rules=SAMD, kind=ClauseKind.PROSE, heading=None, segments=None):
    return triage(
        clause_kind=kind,
        clause_path="제5조",
        path_segments=list(segments or ["제5조"]),
        heading=heading,
        text=text,
        rules=rules,
    )


# --- the modal inventory is closed -----------------------------------------------------------


@pytest.mark.parametrize("modal", MODAL_INVENTORY["ko"])
def test_every_korean_inventory_modal_is_detected(modal: str) -> None:
    """The inventory is fixed at W3-4 and each entry has to be reachable.

    A modal listed in the constant but unmatched by any pattern is worse than one that is absent:
    it reads as covered in review while contributing nothing at runtime.
    """
    assert modal in found_modals(f"제조업자는 기록을 보관{modal}.", SAMD)


def test_conjunction_of_obligations_exposes_both_modals() -> None:
    """ "A 하여야 하며, B 하여야 한다" is a conjunction, not one compound — ADR-0004's fourth row.

    The count is the agent's to produce, but the *precondition* is that the conjunctive form
    ``하여야 하며`` registers as an obligation modal at all. Recognising only the citation form
    would show the model one obligation and a fragment.
    """
    text = "제조업자는 기록을 보관하여야 하며, 매년 그 결과를 보고하여야 한다."
    assert "하여야 한다" in found_modals(text, SAMD)
    assert _triage(text).kind is ClassificationKind.OBLIGATION_BEARING


def test_prohibition_forms_count_as_obligations() -> None:
    assert found_modals("누구든지 이를 판매하여서는 아니 된다.", SAMD)
    assert found_modals("누구든지 이를 판매하여서는 아니된다.", SAMD)


def test_permissive_alone_yields_no_ir() -> None:
    """``할 수 있다`` is not an obligation (ADR-0004 decision 1) — recorded, not skipped."""
    text = "식품의약품안전처장은 필요한 경우 자료의 제출을 요구할 수 있다."
    assert found_modals(text, SAMD) == ()
    assert has_permissive(text, SAMD)

    verdict = _triage(text)
    assert verdict.kind is ClassificationKind.EXCLUDED
    assert verdict.reason is ExclusionReason.PERMISSIVE
    assert not verdict.needs_agent


def test_english_may_not_is_an_obligation_and_may_is_not() -> None:
    """The two are one word apart and mean opposite things."""
    assert "may not" in found_modals("The manufacturer may not distribute the device.", EN)
    assert not has_permissive("The manufacturer may not distribute the device.", EN)
    assert found_modals("The manufacturer may distribute the device.", EN) == ()
    assert has_permissive("The manufacturer may distribute the device.", EN)


# --- structural exclusions -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kind", "reason"),
    [
        (ClauseKind.HEADING, ExclusionReason.HEADING),
        (ClauseKind.FORM, ExclusionReason.FORM),
        (ClauseKind.TABLE, ExclusionReason.TABLE_CONTAINER),
    ],
)
def test_structural_clause_kinds_are_excluded_without_an_llm(kind, reason) -> None:
    verdict = _triage("제조업자는 기록을 보관하여야 한다.", kind=kind)
    assert verdict.kind is ClassificationKind.EXCLUDED
    assert verdict.reason is reason
    assert not verdict.needs_agent


def test_definition_clause_is_excluded_even_when_it_contains_a_modal() -> None:
    """Triage order is load-bearing: role before modal.

    "제2조(정의) … 하여야 한다" carries an inventory modal *inside a definition of a term*. Testing
    modals first would classify it obligation-bearing and manufacture an obligation out of a
    glossary entry.
    """
    verdict = _triage(
        "제2조(정의) 이 규정에서 사용하는 용어의 뜻은 다음과 같다. "
        '1. "기록"이란 보관하여야 하는 자료를 말한다.'
    )
    assert verdict.reason is ExclusionReason.DEFINITION


def test_definition_detected_from_the_embedded_title_when_heading_is_absent() -> None:
    """고시 bodies carry no separate heading — the title is inline in the article text."""
    assert _triage("제2조(정의) 용어의 뜻은 다음과 같다. 보관하여야 한다.").reason is (
        ExclusionReason.DEFINITION
    )
    assert (
        _triage("이 규정의 목적을 달성하여야 한다.", heading="목적").reason is ExclusionReason.SCOPE
    )


def test_delegation_yields_no_ir() -> None:
    """ "…는 총리령으로 정한다" defers the duty; its content lives in another instrument."""
    verdict = _triage("제6조 신고의 절차와 방법에 관하여 필요한 사항은 총리령으로 정한다.")
    assert verdict.reason is ExclusionReason.DELEGATION


def test_transitional_clauses_are_procedural() -> None:
    """부칙 conditions are cited *from* an operative IR, never extracted as one of their own."""
    verdict = _triage("이 규칙은 공포한 날부터 시행하여야 한다.", segments=["부칙", "제1조"])
    assert verdict.reason is ExclusionReason.PROCEDURAL


def test_empty_and_plain_prose_are_still_classified() -> None:
    """There is no unclassified remainder (ADR-0004 decision 6)."""
    assert _triage("").reason is ExclusionReason.EMPTY
    assert _triage("이 표는 참고용이다.").reason is ExclusionReason.NO_OBLIGATION


# --- the domain branch is a rule set ---------------------------------------------------------


def test_domain_branch_changes_only_the_taxonomy_not_the_modals() -> None:
    """ADR-0004 decision 3: the branch is a rule set, not a code path.

    A modal is a property of Korean, not of cosmetics. If the two domains ever diverge on modals,
    the branch has grown past "modal inventory, taxonomy, prompt" and the falsification criterion
    is in play.
    """
    assert SAMD.modals == COSMETIC.modals
    assert SAMD.taxonomy != COSMETIC.taxonomy
    assert set(SAMD.taxonomy) == set(TAXONOMY_CODES[Domain.SAMD])
    assert set(COSMETIC.taxonomy) == set(TAXONOMY_CODES[Domain.COSMETIC])


def test_same_clause_triages_identically_under_both_domains() -> None:
    """One parse pipeline, one triage, two taxonomies. Cross-domain, per the 1.1 falsifier."""
    text = "화장품책임판매업자는 안전성 정보를 보고하여야 한다."
    assert _triage(text, rules=SAMD).kind is _triage(text, rules=COSMETIC).kind


def test_taxonomy_outside_the_domain_is_rejected_not_stored() -> None:
    assert COSMETIC.canonical_taxonomy("ingredient") == "ingredient"
    assert COSMETIC.canonical_taxonomy("design_control") is None  # a SaMD code, not a cosmetic one
    assert SAMD.canonical_taxonomy("Design-Control") == "design_control"
    assert SAMD.canonical_taxonomy("invented") is None


def test_modal_outside_the_inventory_is_rejected() -> None:
    assert SAMD.canonical_modal("하여야 한다") == "하여야 한다"
    assert SAMD.canonical_modal("하여야 하며") == "하여야 한다"  # conjugation → citation form
    assert SAMD.canonical_modal("바람직하다") is None
    assert SAMD.canonical_modal(None) is None


def test_unknown_language_is_refused_rather_than_defaulted() -> None:
    """Extracting an English document with a Korean inventory finds nothing and reports success."""
    with pytest.raises(ValueError, match="No modal inventory"):
        rule_set_for(Domain.SAMD, "fr")
