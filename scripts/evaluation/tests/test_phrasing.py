"""Per-language phrasing, and the two ways an English golden item goes quietly wrong.

The seeder inherited one corpus's shape without saying so: Korean templates, a Korean
article regex, 삭제 for a vacated provision, and a SQL pattern matching only 조 paths.
Pointed at an FDA cell it produced *nothing*, which is the visible failure. The tests
invisible ones: an identifier that looks fabricated and is real, and an item that scores a correct
answer as a failure.
"""

from __future__ import annotations

import pytest
from evaluation.phrasing import ENGLISH, KOREAN, for_language
from evaluation.seed import Article, generate_cross_domain

# --- what counts as the citable unit ------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("Subpart A/820.35", "820.35"),
        ("Subpart A/820.35/(a)/(1)", "820.35"),
        ("Subchapter V/Part A/351", "351"),
        ("Subchapter V/Part A/350a–1/(a)", "350a–1"),
        ("Subpart B/820.20-820.30", "820.20-820.30"),
    ],
)
def test_an_english_section_is_the_segment_that_starts_with_a_digit(path: str, expected) -> None:
    """Containers begin with a letter (``Subpart A``, ``Subchapter V``) and paragraphs with ``(``,
    so this needs no list of container names to stay right when the CFR adds a level."""
    assert ENGLISH.article_segment(path) == expected


def test_an_english_path_with_no_section_has_none() -> None:
    assert ENGLISH.article_segment("Subpart A") is None


def test_korean_is_unchanged_and_a_digit_segment_cannot_claim_a_korean_path() -> None:
    """The gated pair runs on this profile. A CFR-shaped rule leaking into it would re-address the
    MFDS corpus, which is a change to what a gated cell is measured against."""
    assert KOREAN.article_segment("제3장/제1절/제8조/제2항") == "제8조"
    assert KOREAN.article_segment("별표2/표1/행3") is None


# --- an identifier that is provably absent ------------------------------------------------------


@pytest.mark.parametrize(
    ("highest", "offset", "expected"),
    [
        ("820.45", 11, "820.56"),
        ("820.45", 27, "820.72"),
        ("399", 11, "410"),
        ("701.30", 43, "701.73"),
    ],
)
def test_a_fabricated_section_keeps_the_stem_of_the_instrument(highest, offset, expected) -> None:
    """**The trap only works if the number is absent from *this* instrument.** Dropping the stem
    gives ``56``, which is not a CFR section at all; carrying the offset into the stem gives
    ``831.45``, which is a different Part — one that exists. Either turns a question about a
    provision that was never enacted into a question about a real one somewhere else.
    """
    assert ENGLISH.absent_article(highest, offset) == expected


def test_the_korean_form_still_counts_articles_upward() -> None:
    assert KOREAN.absent_article("제35조", 11) == "제46조"


# --- a provision whose address exists and whose content does not --------------------------------


@pytest.mark.parametrize(
    "heading",
    [
        "§ 820.5 [Reserved]",
        "§§ 820.20-820.30 [Reserved]",
        "Repealed. Pub. L. 101–647, title XIX, §1905, Nov. 29, 1990",
        "Omitted",
        "Transferred",
        None,
    ],
)
def test_the_english_markers_for_a_vacated_provision(heading) -> None:
    """Measured against the live corpus on 2026-08-26 rather than guessed: the CFR says
    ``[Reserved]`` and the USC says ``Repealed.`` / ``Omitted`` / ``Transferred``, and those four
    cover every vacated section in the FDA cells."""
    assert ENGLISH.vacant(heading) is True


def test_a_real_provision_is_not_vacated() -> None:
    assert ENGLISH.vacant("§ 820.35 Control of records.") is False
    assert KOREAN.vacant("제5조(영업의 등록)") is False
    assert KOREAN.vacant("삭제 <2013.7.30>") is True


# --- the heading as it reads inside a question --------------------------------------------------


@pytest.mark.parametrize(
    ("heading", "expected"),
    [
        ("§ 820.35 Control of records.", "Control of records"),
        ("§§ 820.20-820.30 [Reserved]", "[Reserved]"),
        ("§ 7.1 Scope.", "Scope"),
    ],
)
def test_a_cfr_heading_does_not_repeat_its_own_identifier(heading, expected) -> None:
    """The template already prints the section, so "820.35 of 21 CFR Part 820 (§ 820.35 Control of
    records.)" says it twice. Korean 조문제목 carry no such prefix and are used as they are."""
    assert ENGLISH.display_heading(heading) == expected


def test_a_korean_heading_is_left_alone() -> None:
    assert KOREAN.display_heading("영업의 등록") == "영업의 등록"


# --- selection ----------------------------------------------------------------------------------


def test_an_unknown_language_raises_rather_than_falling_back() -> None:
    """On the precedent ``rule_set_for`` set. A silent default would seed a Korean question set over
    an English corpus and report the score as a measurement — an unseeded axis is visible, and a
    plausible-looking wrong one is not."""
    with pytest.raises(KeyError, match="no golden-set phrasing"):
        for_language("de")


def test_language_selects_the_profile() -> None:
    assert for_language("ko") is KOREAN
    assert for_language("en") is ENGLISH


# --- the M:N trap -------------------------------------------------------------------------------


def _article(document: str, number: str) -> Article:
    return Article(
        document=document,
        version_id="v",
        clause_path=f"Subpart A/{number}",
        article=number,
        heading=f"§ {number} A real obligation.",
        ordinal=int(float(number)),
        phrasing=ENGLISH,
    )


def test_a_document_the_asking_cell_also_claims_is_never_a_wrong_cell_item() -> None:
    """**Getting this wrong inverts the axis.** ``document_cells`` is M:N over *documents*, so the
    FD&C Act is one Document claimed by both FDA cells with every clause reachable from either. An
    item drawn from it and marked "declining is correct" scores a **correct** answer as a failure —
    phase2.0a *Deviations* 25, as a generator rule rather than a criterion nobody re-reads.
    """
    neighbour = [
        _article("21 U.S.C. chapter 9", "351"),
        _article("21 CFR Part 700", "700.3"),
    ]
    items = generate_cross_domain(
        "samd",
        [("fda_cosmetic", neighbour)],
        ENGLISH,
        frozenset({"21 U.S.C. chapter 9"}),
    )
    assert items
    assert all("21 U.S.C. chapter 9" not in item.question for item in items)
    assert all("21 CFR Part 700" in item.question for item in items)


def test_without_the_exclusion_the_shared_document_would_be_asked() -> None:
    """The guard is doing work, not restating a filter that already existed elsewhere."""
    neighbour = [_article("21 U.S.C. chapter 9", "351")]
    items = generate_cross_domain("samd", [("fda_cosmetic", neighbour)], ENGLISH, frozenset())
    assert items and all("21 U.S.C. chapter 9" in item.question for item in items)
