"""Query parsing, fusion and scope — the deterministic half of ADR-0006 decision 3.

Fusion is tested directly rather than through the database because the claim being made is about
*ordering*, not about SQL: an identifier the user named outright must beat everything the two ranked
arms produced, and a result found by both arms must beat one found deeply by either.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.prompts import build_answer_prompt, passage_text
from app.retrieval import (
    RetrievalResult,
    _scope_dates,
    extract_annex_terms,
    extract_identifier_paths,
    extract_identifiers,
    fuse,
)
from app.store import Hit, build_tsquery
from regops_shared.constants import (
    MAX_CITABLE_PATHS_PER_PASSAGE,
    MAX_PROMPT_BLOCK_CHARS,
)

VERSION = uuid.uuid4()
OTHER_VERSION = uuid.uuid4()


def hit(
    path: str,
    *,
    score: float = 0.5,
    children: tuple[str, ...] = (),
    version: uuid.UUID = VERSION,
    effective: date | None = None,
) -> Hit:
    return Hit(
        clause_id=uuid.uuid4(),
        clause_path=path,
        document_version_id=version,
        heading=None,
        text=f"text of {path}",
        kind="prose",
        effective_date=effective,
        score=score,
        child_clause_paths=children,
    )


# --- identifiers -----------------------------------------------------------------------------


def test_korean_clause_identifiers_are_normalised_to_stored_segments() -> None:
    assert extract_identifiers("화장품법 제 8 조 제1항이 뭐야") == ("제8조", "제1항")


def test_article_with_a_branch_number_stays_distinct() -> None:
    """제8조의2 is a different article from 제8조 — collapsing them answers the wrong question."""
    assert extract_identifiers("제8조의2") == ("제8조의2",)


def test_annex_and_form_identifiers_are_recognised() -> None:
    assert extract_identifiers("별표 1 과 별지 3") == ("별표1", "별지3")


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("what does § 892.2050 require", ("892.2050",)),
        ("21 CFR 892.2050 classification", ("892.2050",)),
        ("21 C.F.R. 700.27", ("700.27",)),
        ("21 U.S.C. 351", ("351",)),
        ("21 USC 351", ("351",)),
        ("§820.35", ("820.35",)),
        # A Part is the *Document* (ADR-0018 decision 1), not a clause address.
        ("21 CFR Part 820 requires", ()),
        # Compound forms belong to extract_identifier_paths — see the test below.
        ("§ 820.35(a)", ()),
    ],
)
def test_us_identifiers_are_normalised_to_the_stored_segment(
    query: str, expected: tuple[str, ...]
) -> None:
    """The captured form must be what ``clauses.path_segments`` holds — ``820.35``, bare.

    This test previously asserted ``("§ 892.2050",)``, **with the sign**, and so locked in a form
    the store cannot match. Measured against the live corpus on 2026-08-25: `21 CFR 892.2050`
    extracted nothing at all, and `§ 820.30(a)(1)` extracted one identifier that returned zero rows
    while the bare `820.35` returned five. The bug was in the extractor and the test agreed with it.
    """
    assert extract_identifiers(query) == expected


def test_a_compound_identifier_becomes_a_path_tail_not_loose_segments() -> None:
    """``(a)`` on its own would match every clause with an ``(a)`` anywhere in scope.

    ``path_segments &&`` is an overlap, so the loose form is worse than no form. The tail is
    matched against the end of ``clause_path`` instead, where the container prefix the user never
    types cannot cause a miss and the siblings cannot cause a hit.
    """
    assert extract_identifier_paths("§ 820.35(a)") == ("820.35/(a)",)
    assert extract_identifier_paths("21 CFR 820.35(a)(3)") == ("820.35/(a)/(3)",)
    assert extract_identifier_paths("21 CFR 820.35") == ()
    assert extract_identifier_paths("화장품법 제8조제1항") == (), "Korean is unchanged here"


def test_a_question_with_no_identifier_yields_none() -> None:
    assert extract_identifiers("안전성 평가 의무가 있나") == ()


# --- annex terms -----------------------------------------------------------------------------


def test_cas_number_is_an_annex_term() -> None:
    assert "65-29-2" in extract_annex_terms("CAS 65-29-2 의 사용한도는?")


def test_korean_particle_is_stripped_from_an_ingredient_name() -> None:
    """The user types 갈라민트리에치오다이드는; the column holds the bare name."""
    terms = extract_annex_terms("갈라민트리에치오다이드는 사용할 수 있나?")

    assert "갈라민트리에치오다이드는" in terms
    assert "갈라민트리에치오다이드" in terms


def test_short_generic_tokens_are_not_annex_terms() -> None:
    """화장품/안전성/평가 all match column values in 별표 1 and 2 — measured, then floored."""
    assert extract_annex_terms("화장품 안전성 평가 의무가 있나") == ()


# --- lexical query ---------------------------------------------------------------------------


def test_tsquery_ors_prefixes_and_particle_stems() -> None:
    """``plainto_tsquery`` ANDs, which over an unstemmed Korean index matches almost nothing."""
    query = build_tsquery("화장품의 안전기준")

    assert "|" in query
    assert "화장품의:*" in query
    assert "화장품:*" in query


def test_tsquery_strips_operator_characters() -> None:
    """A question is user text. Letting `&`/`!` through would make it a boolean expression."""
    assert "&" not in build_tsquery("안전 & 기준 !위험")


def test_tsquery_of_an_empty_question_is_empty() -> None:
    assert build_tsquery("   ") == ""


# --- fusion ----------------------------------------------------------------------------------


def test_exact_identifier_match_outranks_everything_fused() -> None:
    """Acceptance criterion: identifier lookup for a known clause returns it at rank 1."""
    fused = fuse(
        exact=[hit("제8조")],
        rows=[],
        lexical=[hit("제12조"), hit("제3조")],
        vector=[hit("제12조"), hit("제5조")],
        top_k=4,
    )

    assert fused[0].clause_path == "제8조"


def test_exact_annex_row_outranks_a_ranked_paragraph() -> None:
    """Acceptance criterion: the ingredient lookup returns the row, not a neighbouring paragraph."""
    fused = fuse(
        exact=[],
        rows=[hit("별표1/표1/행1", score=1.0)],
        lexical=[hit("별표1/문단2")],
        vector=[hit("별표1/문단2")],
        top_k=3,
    )

    assert fused[0].clause_path == "별표1/표1/행1"


def test_a_prefix_annex_match_does_not_get_the_exact_boost() -> None:
    """Only an equality on the identifier column is a lookup; a prefix is still a candidate."""
    fused = fuse(
        exact=[],
        rows=[hit("별표1/표1/행9", score=0.6)],
        lexical=[hit("제3조"), hit("제4조")],
        vector=[hit("제3조"), hit("제4조")],
        top_k=3,
    )

    assert fused[0].clause_path == "제3조"


def test_agreement_between_arms_beats_a_single_deep_hit() -> None:
    """The whole reason to fuse by rank rather than by score."""
    fused = fuse(
        exact=[],
        rows=[],
        lexical=[hit("A"), hit("B"), hit("C")],
        vector=[hit("C"), hit("D"), hit("E")],
        top_k=1,
    )

    assert fused[0].clause_path == "C"


def test_fusion_keeps_the_copy_that_carries_child_paths() -> None:
    """Only the vector arm knows what a passage covers; losing it narrows what may be cited."""
    fused = fuse(
        exact=[],
        rows=[],
        lexical=[hit("제8조")],
        vector=[hit("제8조", children=("제8조/제1항",))],
        top_k=1,
    )

    assert fused[0].child_clause_paths == ("제8조/제1항",)


# --- citable set -----------------------------------------------------------------------------


def test_citable_paths_include_the_children_of_a_retrieved_article() -> None:
    """Decision 1's split granularity, expressed as the permission generation actually gets."""
    result = RetrievalResult(hits=[hit("제8조", children=("제8조/제1항", "제8조/제2항"))])

    assert result.citable_paths() == {
        (VERSION, "제8조"),
        (VERSION, "제8조/제1항"),
        (VERSION, "제8조/제2항"),
    }


def test_citable_paths_are_version_scoped() -> None:
    """A path is not citable in a version retrieval never touched, even if it exists there."""
    result = RetrievalResult(hits=[hit("제8조", version=VERSION)])

    assert (OTHER_VERSION, "제8조") not in result.citable_paths()


# --- effective dates -------------------------------------------------------------------------


TODAY = date(2026, 8, 11)


def test_straddling_clauses_are_flagged_not_resolved() -> None:
    """Acceptance criterion: an answer whose clauses straddle the boundary says so."""
    result = RetrievalResult(
        hits=[
            hit("제8조", effective=date(2026, 4, 2)),
            hit("제9조", effective=date(2027, 1, 1)),
        ]
    )

    _scope_dates(result, today=TODAY)

    assert result.straddles_effective_date
    assert result.effective_date_scope == date(2026, 4, 2)


def test_clauses_in_force_together_do_not_straddle() -> None:
    result = RetrievalResult(
        hits=[hit("제8조", effective=date(2025, 1, 1)), hit("제9조", effective=date(2026, 4, 2))]
    )

    _scope_dates(result, today=TODAY)

    assert not result.straddles_effective_date
    assert result.effective_date_scope == date(2026, 4, 2)


def test_all_pending_reports_the_nearest_date_and_does_not_straddle() -> None:
    """Nothing in force yet is a real state, and it is not the same as a straddle."""
    result = RetrievalResult(
        hits=[hit("제8조", effective=date(2027, 1, 1)), hit("제9조", effective=date(2028, 1, 1))]
    )

    _scope_dates(result, today=TODAY)

    assert not result.straddles_effective_date
    assert result.effective_date_scope == date(2027, 1, 1)


def test_unresolvable_dates_leave_the_scope_null() -> None:
    """ADR-0013: a date that could not be resolved stays null rather than being computed."""
    result = RetrievalResult(hits=[hit("제8조"), hit("제9조")])

    _scope_dates(result, today=TODAY)

    assert result.effective_date_scope is None
    assert not result.straddles_effective_date


# --- prompt bounds ---------------------------------------------------------------------------


def test_a_huge_clause_is_bounded_before_it_reaches_the_model() -> None:
    """Measured, not hypothetical: one 별표 clause put 130,603 characters into a live prompt.

    ``MAX_PASSAGE_CHARS`` caps what gets *embedded*; a retrieval hit carries the raw clause text and
    had no bound at all. Eight such hits came to ≈58,000 tokens against a 32,768 window, which
    Ollama truncates silently — a three-minute timeout, and a model citing text it never saw.
    """
    giant = Hit(
        clause_id=uuid.uuid4(),
        clause_path="별표8/-1/Ⅱ",
        document_version_id=VERSION,
        heading=None,
        text="가" * 130_603,
        kind="prose",
        effective_date=None,
        score=0.019,
    )

    body = passage_text(giant)

    assert len(body) <= MAX_PROMPT_BLOCK_CHARS + 32  # + the truncation marker
    assert "truncated" in body


def test_the_stored_passage_is_preferred_over_the_raw_clause_text() -> None:
    """It is bounded, and it is the unit the vector actually scored."""
    hit_with_passage = Hit(
        clause_id=uuid.uuid4(),
        clause_path="제8조",
        document_version_id=VERSION,
        heading=None,
        text="raw clause text",
        kind="prose",
        effective_date=None,
        score=1.0,
        passage="assembled 조-level passage",
    )

    assert passage_text(hit_with_passage) == "assembled 조-level passage"


def test_the_citable_list_is_capped() -> None:
    """A 조 with hundreds of 호 would spend more prompt on addresses than on text."""
    crowded = hit("제8조", children=tuple(f"제8조/제{n}호" for n in range(200)))

    prompt = build_answer_prompt(
        question="q",
        hits=[crowded],
        versions=[],
        effective_date_scope=None,
        straddles=False,
    )

    assert prompt.count("제8조/제") <= MAX_CITABLE_PATHS_PER_PASSAGE
