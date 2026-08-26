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
    INHERITABLE_REASONS,
    found_modals,
    has_permissive,
    rule_set_for,
    triage,
)
from regops_shared.constants import (
    IR_RULE_VERSION,
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


# --- the English rule set, against the shapes the FDA corpus actually contains -----------------
#
# Verified end to end on 2026-08-25 over 2,039 real CFR clauses: 357 obligation-bearing, with every
# inventory modal firing (must 229, shall 116, is required to 16, may not 13). These cases pin the
# behaviour that measurement confirmed, and the two *absences* that measurement also confirmed.


def _en(text: str, *, heading: str | None = None, segments=None):
    return triage(
        clause_kind=ClauseKind.PROSE,
        clause_path="Subpart A/820.35",
        path_segments=list(segments or ["Subpart A", "820.35"]),
        heading=heading,
        text=text,
        rules=EN,
    )


@pytest.mark.parametrize("modal", MODAL_INVENTORY["en"])
def test_every_english_inventory_modal_is_detected(modal: str) -> None:
    """The English mirror of the Korean inventory test. All four fire in the live corpus."""
    sentence = {
        "shall": "The manufacturer shall maintain records of the review.",
        "must": "The manufacturer must include the following information.",
        "is required to": "Each establishment is required to register annually.",
        "may not": "A device may not be introduced into interstate commerce.",
    }[modal]
    assert modal in found_modals(sentence, EN)


def test_shall_not_be_construed_is_not_an_obligation() -> None:
    """The negative lookahead in the ``shall`` pattern: a construction clause imposes nothing.

    **A precaution rather than a measured need, and worth saying so.** Searched on 2026-08-25:
    "shall not be construed", "shall be construed" and "may not be construed" each return **zero**
    across the FDA corpus. The guard covers exactly one phrasing — the one written into the
    pattern — and the sibling form ``shall be construed`` is *not* covered. Neither occurs, so
    neither is load-bearing today; if one ever does, this is the test that should grow.
    """
    assert found_modals("This section shall not be construed to require a submission.", EN) == ()
    # The uncovered sibling, pinned so the asymmetry is visible rather than surprising.
    assert found_modals("Nothing here shall be construed to limit the authority.", EN) == ("shall",)


# --- the CFR heading shape ----------------------------------------------------------------------


def test_a_cfr_scope_heading_is_excluded() -> None:
    """The eCFR heading is ``§ 892.1 Scope.`` — number, title, period. 8 matched in the corpus."""
    verdict = _en(
        "This part sets forth the classification of radiology devices.", heading="§ 892.1 Scope."
    )
    assert verdict.reason is ExclusionReason.SCOPE


def test_a_cfr_definitions_heading_is_excluded() -> None:
    verdict = _en("As used in this subchapter:", heading="§ 700.3 Definitions.")
    assert verdict.reason is ExclusionReason.DEFINITION


def test_scope_inside_a_longer_word_does_not_exclude_the_clause() -> None:
    """``endoscope`` contains ``scope``. A substring test would drop an obligation-bearing clause
    while coverage still counted it examined — the quietest way to lose one."""
    verdict = _en(
        "The manufacturer must validate the sterilization process.",
        heading="§ 876.1500 Endoscope and accessories.",
    )
    assert verdict.kind is ClassificationKind.OBLIGATION_BEARING


# --- the two heuristics with no CFR counterpart, and why -----------------------------------------


def test_a_cross_reference_is_not_a_delegation() -> None:
    """Measured: the FDA corpus has **zero** delegation forms and 46 cross-references.

    A cross-reference says where the detail lives; a delegation says someone else will decide the
    duty. Treating "in accordance with part 807" as delegation would silently exclude 39 clauses
    that do state obligations, which is why ``_DELEGATION`` stays Korean-only.
    """
    verdict = _en(
        "All owners must register in accordance with part 807 of this chapter.",
    )
    assert verdict.kind is ClassificationKind.OBLIGATION_BEARING
    assert verdict.reason is not ExclusionReason.DELEGATION


def test_a_cfr_clause_is_never_transitional() -> None:
    """A CFR Part carries no 부칙: effective dates live in the Federal Register rule, which this
    pipeline models as an announcement rather than as codified text (ADR-0019)."""
    verdict = _en(
        "Each manufacturer must establish and maintain procedures.",
        segments=["Subpart B", "820.30", "(a)"],
    )
    assert verdict.reason is not ExclusionReason.PROCEDURAL


# --- the falsifier the language split exists for --------------------------------------------------


def test_an_english_clause_under_the_korean_rule_set_finds_nothing() -> None:
    """Why ``rule_set_for`` refuses an unknown language instead of falling back.

    Extracting an English document under the Korean inventory finds no modal and reports full
    coverage — a silent zero rather than an error.
    """
    english = "The manufacturer shall maintain records of the review."
    assert found_modals(english, EN) == ("shall",)
    assert found_modals(english, SAMD) == ()


# --- the SaMD taxonomy, and the measurement that grew it ------------------------------------------
#
# Triaged over the FDA corpus on 2026-08-25: Part 820 supplies 21 of 341 obligation-bearing SaMD
# clauses, so the original four codes described 6% of them. These cases pin what the other 94% is
# for, and the boundary that was deliberately not crossed.


def test_the_original_four_codes_survive_the_addition() -> None:
    """Existing IRs carry these; dropping one would orphan them."""
    for code in ("design_control", "risk", "vnv", "postmarket"):
        assert code in TAXONOMY_CODES[Domain.SAMD]


@pytest.mark.parametrize("code", ["registration", "classification", "records"])
def test_each_added_code_has_a_part_behind_it(code: str) -> None:
    """No speculative codes: 807 registration & listing, 892+860 classification, 11 records."""
    assert code in TAXONOMY_CODES[Domain.SAMD]


def test_postmarket_is_the_only_code_that_absorbs_several_parts() -> None:
    """MDR, surveillance, corrections/removals and recalls are one idea — duties that attach after
    a device is on the market. Splitting them would multiply codes without separating obligations
    an RA treats differently."""
    assert TAXONOMY_CODES[Domain.SAMD].count("postmarket") == 1


def test_the_taxonomy_carries_no_premarket_catch_all() -> None:
    """The rejected alternative was filing 892/807/860/11 under ``postmarket``.

    They are pre-market and market-entry duties, so that label would be false — worse than no code,
    because a wrong one reads as information.
    """
    samd = TAXONOMY_CODES[Domain.SAMD]
    assert "premarket" not in samd, "a catch-all was added instead of naming the duty"
    assert {"registration", "classification"} <= set(samd)


def test_the_cosmetic_taxonomy_is_untouched() -> None:
    """Assessed and left alone, which is not the same as unexamined.

    All four cosmetic Parts are ingested (2026-08-25) and the five codes cover every obligation:
    ``labelling`` takes 701 (63) and 740 (12), ``ingredient`` takes 700 (16 — CFC propellants,
    prohibited cattle materials, sunscreen ingredients). Part 710 yields none at all, consistent
    with being the *voluntary* Part. ``claims``/``gmp``/``notification`` are unexercised here and
    kept: they serve the MFDS cell, and MoCRA's registration duties live in the FD&C Act and
    Cosmetics Direct rather than in these Parts.
    """
    assert TAXONOMY_CODES[Domain.COSMETIC] == (
        "ingredient",
        "labelling",
        "claims",
        "gmp",
        "notification",
    )


def test_the_rule_version_moved_with_the_taxonomy() -> None:
    """An IR extracted under a different taxonomy is not comparable with one extracted under this,
    which is the whole reason the version is stamped on every row.

    **This assertion pins the number and not the rules, and 1.3.0 is what that cost.** Two commits
    changed what the rule set does — anchoring the role test, and letting a definition descend — and
    this test passed through both, because neither touched the constant it reads. 21 CFR Part 700
    then produced 21 IRs and later 18, twice, all three runs stamped ``1.3.0``.

    Pinning the rule *content* to the version is the gate that would have failed here. It does not
    exist yet.
    """
    assert IR_RULE_VERSION == "1.4.0"
    assert rule_set_for(Domain.SAMD, "en").rule_version == IR_RULE_VERSION


def test_adding_codes_did_not_touch_the_modal_inventory() -> None:
    """*Whether* a clause bears an obligation is unchanged; only the label it can carry moved."""
    assert rule_set_for(Domain.SAMD, "en").modals == MODAL_INVENTORY["en"]
    assert rule_set_for(Domain.SAMD, "ko").modals == MODAL_INVENTORY["ko"]


# --- a heading must BE the role, not mention it ---------------------------------------------------


@pytest.mark.parametrize(
    ("heading", "reason"),
    [
        ("정의", ExclusionReason.DEFINITION),
        ("용어의 정의", ExclusionReason.DEFINITION),
        ("목적", ExclusionReason.SCOPE),
        ("적용범위", ExclusionReason.SCOPE),
        ("적용 범위", ExclusionReason.SCOPE),
    ],
)
def test_a_korean_role_heading_is_still_excluded(heading, reason) -> None:
    """Anchoring must not cost the genuine ones. These four are every role heading in the gated
    corpus, measured rather than imagined."""
    assert _triage("어떤 내용이든 상관없다.", heading=heading).reason is reason


@pytest.mark.parametrize(
    "heading",
    [
        "지정의 취소 등",
        "적합성인정의 취소 등",
        "사용목적",
        "전시 목적 의료기기의 진열 승인 등",
        "임상시험용 의료기기의 치료목적 사용",
        "쉬운 용어",
        "번호 | 분류번호 | 품목명 | 등급 | 정의",
    ],
)
def test_a_korean_word_containing_the_role_does_not_exclude_the_clause(heading) -> None:
    """**The Korean half of the `endoscope` bug, and it was live.** The ASCII needles were guarded
    with `\b`; Hangul has no word boundary for `\b` to find, so the Korean ones fell through to
    plain containment — 지**정의**, 적합성인**정의**, 사용**목적** — and excluded obligation-bearing
    articles that then never reached the agent, while coverage counted them as examined.

    Every heading here is real: taken from the gated corpus on 2026-08-26, and the last one is a
    table header row.
    """
    verdict = _triage("제조업자는 그 기록을 3년간 보관하여야 한다.", heading=heading)
    assert verdict.kind is ClassificationKind.OBLIGATION_BEARING


# --- a sub-provision keeps the role of the provision above it -------------------------------------


def _inherited(text: str, *, path: str, inherited: ExclusionReason | None):
    return triage(
        clause_kind=ClauseKind.PROSE,
        clause_path=path,
        path_segments=path.split("/"),
        heading=None,
        text=text,
        rules=SAMD,
        inherited=inherited,
    )


def test_a_paragraph_of_a_definitions_article_is_a_definition() -> None:
    """A definitions article states its heading once and its 호 simply define terms, so reading each
    clause alone sends them to the agent. That is how 21 CFR 700.3(g) — *"The term chemical
    description means…"* — produced an IR asserting an obligation a definition cannot impose."""
    verdict = _inherited(
        '2. "의료기기 고유식별자"란 제품별로 고유하게 생성되는 숫자 또는 문자의 조합을 말한다.',
        path="제2조/제2호",
        inherited=ExclusionReason.DEFINITION,
    )
    assert verdict.kind is ClassificationKind.EXCLUDED
    assert verdict.reason is ExclusionReason.DEFINITION


def test_a_modal_inside_an_inherited_definition_does_not_rescue_it() -> None:
    """The same ordering the article-level test already relies on: a definition that happens to
    contain 하여야 한다 is still a definition, and that holds one level down too."""
    verdict = _inherited(
        '3. "표시"란 용기에 기재하여야 하는 사항을 말한다.',
        path="제2조/제3호",
        inherited=ExclusionReason.DEFINITION,
    )
    assert verdict.reason is ExclusionReason.DEFINITION


def test_structure_still_wins_over_an_inherited_role() -> None:
    """An empty stub inside a definitions article is empty, not a definition. The inheritance is
    checked after the structural tests for exactly this reason."""
    verdict = _inherited("", path="제2조/제4호", inherited=ExclusionReason.DEFINITION)
    assert verdict.reason is ExclusionReason.EMPTY


def test_nothing_is_inherited_when_the_provision_above_carries_no_role() -> None:
    verdict = _inherited(
        "제조업자는 그 기록을 3년간 보관하여야 한다.", path="제5조/제1항", inherited=None
    )
    assert verdict.kind is ClassificationKind.OBLIGATION_BEARING


def test_only_role_reasons_are_inheritable() -> None:
    """`permissive`, `delegation` and the rest describe *this clause*. A sub-clause of a permissive
    paragraph can carry a duty of its own, and inheriting the parent's verdict would bury it."""
    assert ExclusionReason.PERMISSIVE not in INHERITABLE_REASONS
    assert ExclusionReason.DELEGATION not in INHERITABLE_REASONS
    assert ExclusionReason.NO_OBLIGATION not in INHERITABLE_REASONS
    assert frozenset({ExclusionReason.DEFINITION, ExclusionReason.SCOPE}) == INHERITABLE_REASONS
