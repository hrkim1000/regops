"""The ``usc_text`` profile, and the ladder it shares with ``cfr_structured``.

Every rule asserted here was **measured against 21 U.S.C. chapter 9** on 2026-08-25 rather than
assumed from the drafting manuals — the counts in each docstring are from that corpus
(``docs/design/spike-2026-08-24-fda-source-recon.md``). Three of them were wrong on the first
reading, and each cost real clauses:

* the alphabet past ``z`` (base-26 vs doubled), which mis-nested every subsection after ``(bb)``;
* the level below ``(I)``, whose absence pushed 14 item-level ``(aa)`` designators in
  21 U.S.C. 355 up to subsection level;
* compound designators, whose absence pushed nested ``(i)`` clauses up to subsection level, where
  they collided with the section's own subsection ``(i)``.

No test reaches the network; the fixtures are the shapes the live granule returned.
"""

from __future__ import annotations

import pytest

from app.parsing import parse_document, profile_for
from app.parsing.ladder import CFR, USC, base26_alpha, designator_run, doubled_alpha, doubled_only
from app.parsing.model import ParseError
from app.parsing.usc import PROFILE
from regops_shared.constants import DocType, DriftSignal


def _granule(body: str) -> bytes:
    """Wrap statutory blocks in the container chrome govinfo puts around every granule."""
    return (
        '<html><body><p class="chapter-head">CHAPTER 9 - FEDERAL FOOD, DRUG, AND COSMETIC ACT</p>'
        '<p class="subchapter-head">SUBCHAPTER V - DRUGS AND DEVICES</p>'
        '<p class="part-head">Part A - Drugs and Devices</p>' + body + "</body></html>"
    ).encode()


def _parse(body: str):
    return parse_document(
        _granule(body), doc_type=DocType.CODIFIED_STATUTE, canonical_key="fda:usc:21-9"
    )


def _paths(parsed) -> list[str]:
    return [clause.clause_path for clause in parsed.clauses]


# --- registration ----------------------------------------------------------------------------


def test_the_profile_is_selected_by_doc_type() -> None:
    """Selection is ``doc_type`` and nothing else — ADR-0002 decision 3.

    A ``CODIFIED_STATUTE`` exists precisely so this routing needs no branch on authority: ``LAW``
    still means 법률 and still goes to ``law_structured``.
    """
    assert profile_for(DocType.CODIFIED_STATUTE) == PROFILE == "usc_text"
    assert profile_for(DocType.LAW) == "law_structured"


def test_html_that_is_not_well_formed_xml_still_parses() -> None:
    """The live granule fails ``defusedxml`` on its first character reference.

    This is the whole reason the profile declares ``ACCEPTS_RAW``: routing a USC granule through
    the registry's XML gate would fail at the envelope, before reaching a provision.
    """
    parsed = _parse(
        '<h3 class="section-head">&sect;351. Adulterated</h3><p class="statutory-body">(a) text</p>'
    )
    assert _paths(parsed)[0] == "Subchapter V/Part A/351"


# --- what is law, and what is apparatus ------------------------------------------------------


def test_editorial_notes_are_not_clauses() -> None:
    """The chapter carries 4,149 ``note-body`` blocks against 2,061 ``statutory-body``.

    The Office of the Law Revision Counsel's apparatus outweighs the enacted text it annotates.
    Admitting it would put text that was never enacted into citations and into the extraction
    denominator.
    """
    parsed = _parse(
        '<h3 class="section-head">§351. Adulterated</h3>'
        '<p class="statutory-body">(a) enacted text</p>'
        '<p class="source-credit">(June 25, 1938, ch. 675, §501)</p>'
        '<p class="note-head">Editorial Notes</p>'
        '<p class="note-body">(b) 1997—Subsec. (a) amended by Pub. L. 105-115</p>'
    )
    texts = " ".join(clause.text for clause in parsed.clauses)
    assert "enacted text" in texts
    assert "1997" not in texts
    assert "Subchapter V/Part A/351/(b)" not in _paths(parsed)


def test_the_ambiguous_style_is_read_by_position_not_by_name() -> None:
    """``Q04`` appears 1,259 times and is used on **both** sides of the line.

    It carries enacted text and it carries note banners, so no class-name rule can separate them.
    Position can: inside the section body it is law, after the source credit it is apparatus.
    """
    parsed = _parse(
        '<h3 class="section-head">§351. Adulterated</h3>'
        '<p class="Q04">(a) enacted through the ambiguous style</p>'
        '<p class="source-credit">(June 25, 1938, ch. 675)</p>'
        '<p class="Q04">Statutory Notes and Related Subsidiaries</p>'
    )
    texts = " ".join(clause.text for clause in parsed.clauses)
    assert "enacted through the ambiguous style" in texts
    assert "Statutory Notes" not in texts


def test_the_source_credit_is_not_kept_as_a_provision_or_as_an_identifier() -> None:
    """Public Law history is provenance about the instrument, not a provision of it.

    ``cfr_structured`` excludes ``<SOURCE>`` and ``<CITA>`` for exactly this reason. It is also not
    an *identifier*: ``clauses.source_ref`` holds the authority's own 조문키 and is the primary
    renumber signal, it is ``varchar(64)``, and 21 U.S.C. 321's credit runs past two thousand
    characters — writing it there raised ``StringDataRightTruncation`` on the live corpus.
    """
    parsed = _parse(
        '<h3 class="section-head">§351. Adulterated</h3>'
        '<p class="statutory-body">(a) text</p>'
        '<p class="source-credit">(June 25, 1938, ch. 675, §501, 52 Stat. 1049.)</p>'
    )
    assert all(clause.source_ref is None for clause in parsed.clauses)
    assert all("52 Stat. 1049" not in clause.text for clause in parsed.clauses)


def test_a_repealed_section_is_kept() -> None:
    """Seven sections in the chapter are repealed, omitted or transferred.

    Dropping them would make ``21 U.S.C. 333a`` unresolvable, when the answer an RA needs is
    exactly that it was repealed.
    """
    parsed = _parse(
        '<h3 class="section-head">§333a. Repealed. Pub. L. 101–647, §1905, Nov. 29, 1990</h3>'
    )
    assert "Subchapter V/Part A/333a" in _paths(parsed)


def test_a_body_with_no_section_head_is_drift() -> None:
    """Fail before a version is written — ADR-0003 decision 6."""
    with pytest.raises(ParseError) as caught:
        _parse('<p class="note-body">only apparatus</p>')
    assert caught.value.signal is DriftSignal.ZERO_CLAUSES


# --- the ladder ------------------------------------------------------------------------------


def test_the_usc_alphabet_doubles_past_z() -> None:
    """21 U.S.C. 321 runs ``… y z aa bb cc dd ee ff gg hh ii jj kk ll mm nn oo``.

    Read base-26, ``(bb)`` is the 54th designator rather than the 28th, no open level continues it,
    and every subsection from ``(bb)`` on is mis-nested.
    """
    assert doubled_alpha("z") == 26
    assert doubled_alpha("aa") == 27
    assert doubled_alpha("bb") == 28
    assert base26_alpha("bb") == 54, "the CFR convention, kept for the CFR"
    assert doubled_alpha("ab") is None, "not a designator in this convention"


def test_the_item_level_starts_at_a_doubled_letter() -> None:
    """``(aa)`` is the 27th subsection *and* the 1st item, and 21 U.S.C. 355 uses it both ways."""
    assert doubled_only("aa") == 1
    assert doubled_only("bb") == 2
    assert doubled_only("a") is None


def test_a_subsection_aa_and_an_item_aa_land_at_different_depths() -> None:
    """The same token, resolved by sequence rather than by style. See ``Ladder.depth_for``."""
    after_z = [("(z)", USC.styles[0], 0)]
    assert USC.depth_for("aa", after_z) == 0

    deep = [
        ("(a)", USC.styles[0], 0),
        ("(1)", USC.styles[1], 1),
        ("(C)", USC.styles[2], 2),
        ("(ii)", USC.styles[3], 3),
        ("(I)", USC.styles[4], 4),
    ]
    assert USC.depth_for("aa", deep) == 5


def test_the_two_conventions_order_their_levels_differently() -> None:
    """The CFR nests ``(a)(1)(i)(A)``; the USC nests ``(a)(1)(A)(i)(I)``.

    govinfo declares the USC order in its own markup: ``subparagraph-head`` is uppercase alpha 863
    times and ``clause-head`` is lowercase roman, which is the reverse of the CFR's third and
    fourth rungs.
    """
    assert USC.style_at(2) != CFR.style_at(2)
    assert USC.style_at(2) == CFR.style_at(3)
    assert USC.style_at(3) == CFR.style_at(2)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("(3)(A) Except as provided in subparagraph (B), no libel", ["3", "A"]),
        ("(i)(I) the food's advertising which resulted in", ["i", "I"]),
        ("(a) text", ["a"]),
        ('(a) The term "pesticide" (as defined) means', ["a"]),
        ("no designator at all", []),
    ],
)
def test_a_designator_run_needs_adjacency(text: str, expected: list[str]) -> None:
    """Adjacency is what separates a nesting from a parenthetical.

    ``(3)(A)`` opens two levels; ``(a) … (as defined)`` opens one, because prose has a space in
    front of it.
    """
    assert designator_run(text) == expected


def test_a_compound_designator_opens_both_levels() -> None:
    """Reading only ``(3)`` leaves the ``(A)`` level closed, and then ``(i)`` has nothing to nest
    under — which is how 21 U.S.C. 334's clauses ended up beside its subsections."""
    parsed = _parse(
        '<h3 class="section-head">§334. Seizure</h3>'
        '<p class="statutory-body">(a) Grounds</p>'
        '<p class="statutory-body">(3)(A) Except as provided in subparagraph (B)</p>'
        '<p class="statutory-body-1em">(i) is misbranded</p>'
    )
    paths = _paths(parsed)
    assert "Subchapter V/Part A/334/(a)/(3)/(A)" in paths
    assert "Subchapter V/Part A/334/(a)/(3)/(A)/(i)" in paths
    assert "Subchapter V/Part A/334/(i)" not in paths, "a clause must not reach subsection level"


def test_an_intermediate_level_carries_its_own_label() -> None:
    """Paragraph ``(3)`` of ``(3)(A) Except as provided…`` states nothing except that its content
    is its subparagraphs, and a citation to it still has to resolve."""
    parsed = _parse(
        '<h3 class="section-head">§334. Seizure</h3>'
        '<p class="statutory-body">(a) Grounds</p>'
        '<p class="statutory-body">(3)(A) Except as provided</p>'
    )
    by_path = {clause.clause_path: clause.text for clause in parsed.clauses}
    assert by_path["Subchapter V/Part A/334/(a)/(3)"] == "(3)"
    assert by_path["Subchapter V/Part A/334/(a)/(3)/(A)"].startswith("(3)(A) Except")


# --- addressing ------------------------------------------------------------------------------


def test_containers_are_segments_and_the_chapter_is_not() -> None:
    """``21 U.S.C. 351(a)(1)`` stores as ``Subchapter V/Part A/351/(a)/(1)``.

    The chapter is the Document, so it is not a segment inside itself — the same rule
    ``cfr_structured`` applies to a Part.
    """
    parsed = _parse(
        '<h3 class="section-head">§351. Adulterated drugs and devices</h3>'
        '<p class="statutory-body">(a) Poisonous ingredients</p>'
        '<p class="statutory-body">(1) If it consists in whole or in part</p>'
    )
    paths = _paths(parsed)
    assert paths[0] == "Subchapter V/Part A/351"
    assert "Subchapter V/Part A/351/(a)/(1)" in paths
    assert not any(path.startswith("Chapter") for path in paths)


def test_the_section_heading_is_kept_separately_from_its_text() -> None:
    parsed = _parse('<h3 class="section-head">§351. Adulterated drugs and devices</h3>')
    assert parsed.clauses[0].heading == "Adulterated drugs and devices"


# --- depth the authority states, versus depth we infer -----------------------------------------

#: The `(i)` collision, in the shape 21 U.S.C. 335a has it: subsections run to `(h)`, a paragraph
#: three levels down opens a roman `(i)`, and the section's own `(i)` follows. `(i)` is both the
#: ninth letter and the first roman, so the designator alone cannot separate them — but the Office
#: of the Law Revision Counsel marks its subsections `subsection-head` and says which is which.
AMBIGUOUS_I = (
    '<h3 class="section-head">&sect;335a. Debarment</h3>'
    '<p class="subsection-head">(h) Termination of suspension</p>'
    '<p class="statutory-body">The Secretary may terminate a suspension.</p>'
    '<p class="statutory-body-1em">(1) In general</p>'
    '<p class="statutory-body-2em">(A) The person shall&mdash;</p>'
    '<p class="statutory-body-3em">(i) fully remedy the patterns or practices; and</p>'
    '<p class="statutory-body-3em">(ii) demonstrate that it will operate lawfully.</p>'
    '<p class="subsection-head">(i) Procedure</p>'
    '<p class="statutory-body">The Secretary may not take any action under subsection (a).</p>'
)

#: 21 U.S.C. 355 really does carry two subsections `(z)`, and the source says so in as many words:
#: footnote 6 reads *"So in original. Two subsecs. (z) have been enacted."*
TWO_Z = (
    '<h3 class="section-head">&sect;355. New drugs</h3>'
    '<p class="subsection-head">(z) Nonclinical test defined</p>'
    '<p class="statutory-body">For purposes of this section the term is defined.</p>'
    '<p class="subsection-head">(z) Diversity action plan for clinical studies</p>'
    '<p class="statutory-body">A sponsor shall submit a plan.</p>'
)

_PREFIX = "Subchapter V/Part A/"


def test_a_roman_three_levels_down_is_not_the_subsection_after_h() -> None:
    """Both readings are well-formed and only one is right. The deep `(i)` is a perfect successor to
    subsection `(h)`, so reading it that way closes three levels and files the provision at
    subsection depth — where the section's real `(i)` then lands on the same path. 16 of the FD&C
    Act's 23 duplicate clause paths were this."""
    paths = _paths(_parse(AMBIGUOUS_I))
    assert f"{_PREFIX}335a/(h)/(1)/(A)/(i)" in paths
    assert f"{_PREFIX}335a/(h)/(1)/(A)/(ii)" in paths


def test_the_subsection_the_authority_named_is_placed_where_it_said() -> None:
    """`subsection-head` is not presentational — it is the OLRC naming the level. The `-Nem`
    suffixes stay ignored, and for a different reason: a compound run like `(h)(1)(A)` is indented
    at its outermost new level, so the indent does not state what the paragraph opens."""
    paths = _paths(_parse(AMBIGUOUS_I))
    assert f"{_PREFIX}335a/(i)" in paths
    # It did not have to be suffixed, because nothing else claimed the path.
    assert f"{_PREFIX}335a/(i)~2" not in paths


def test_a_designator_the_authority_enacted_twice_keeps_both_provisions() -> None:
    """This is what `_disambiguate` is *for*, and telling it apart from our own mis-nesting is the
    whole point of the distinction. Dropping the second would lose an obligation while the clause
    count still looked plausible; the `~2` suffix is deterministic, so a citation resolves."""
    parsed = _parse(TWO_Z)
    paths = _paths(parsed)
    assert f"{_PREFIX}355/(z)" in paths
    assert f"{_PREFIX}355/(z)~2" in paths
    by_path = {c.clause_path: c for c in parsed.clauses}
    assert "Nonclinical" in by_path[f"{_PREFIX}355/(z)"].text
    assert "Diversity" in by_path[f"{_PREFIX}355/(z)~2"].text
