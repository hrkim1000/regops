"""``cfr_structured`` — the fourth parser profile.

Fixtures are hand-built from shapes observed live in title 21 on 2026-08-24
(``docs/design/spike-2026-08-24-fda-source-recon.md``), following the convention in
``test_parsing.py``: exercise what actually bit, not what is easy to invent. So the section here
opens with an unlabelled paragraph and carries an ``<I>`` run-in heading because 820.35 does; the
range-named nodes are here because the QMSR left ``820.20-820.30`` and subpart ``C-O`` behind; and
the ``(h)`` → ``(i)`` case is here because that is the one a style-keyed parser gets wrong.
"""

from __future__ import annotations

import pytest

from app.parsing import ParseError, parse_document, profile_for
from app.parsing.cfr import PROFILE
from regops_shared.constants import ClauseKind, DocType, DriftSignal

# --- fixtures ------------------------------------------------------------------------------

PART_XML = """<?xml version="1.0"?>
<DIV5 N="820" TYPE="PART"
 hierarchy_metadata="{&quot;citation&quot;:&quot;21 CFR Part 820&quot;}">
<HEAD>PART 820&#x2014;QUALITY MANAGEMENT SYSTEM REGULATION</HEAD>
<AUTH><HED>Authority:</HED><PSPACE>21 U.S.C. 351, 352, 360.</PSPACE></AUTH>
<SOURCE><HED>Source:</HED>
<PSPACE>89 FR 7523, Feb. 2, 2024, unless otherwise noted.</PSPACE></SOURCE>
<DIV6 N="A" TYPE="SUBPART"
 hierarchy_metadata="{&quot;citation&quot;:&quot;21 CFR Part 820 Subpart A&quot;}">
<HEAD>Subpart A&#x2014;General Provisions</HEAD>
<DIV8 N="820.35" TYPE="SECTION"
 hierarchy_metadata="{&quot;citation&quot;:&quot;21 CFR 820.35&quot;}">
<HEAD>&#xA7; 820.35 Control of records.</HEAD>
<P>In addition to the requirements of Clause 4.2.5 in ISO 13485, the manufacturer
must include the following information:</P>
<P>(a) <I>Records of complaints.</I> The manufacturer shall maintain records of the review.</P>
<P>(1) The name of the device;</P>
<P>(2) The date the complaint was received;</P>
<P>(b) <I>Records of servicing.</I> Each manufacturer shall analyze servicing records.</P>
<CITA TYPE="N">[61 FR 52654, Oct. 7, 1996,
as amended at 65 FR 17136, Mar. 31, 2000]</CITA>
</DIV8>
<DIV8 N="820.20-820.30" TYPE="SECTION"
 hierarchy_metadata="{&quot;citation&quot;:&quot;21 CFR 820.20-820.30&quot;}">
<HEAD>&#xA7;&#xA7; 820.20-820.30 [Reserved]</HEAD>
</DIV8>
</DIV6>
<DIV6 N="C-O" TYPE="SUBPART">
<HEAD>Subparts C-O [Reserved]</HEAD>
</DIV6>
</DIV5>
"""

#: (h) then (i): a style-keyed parser reads the second as roman and nests it. It is a sibling.
SIBLING_I_XML = """<?xml version="1.0"?>
<DIV8 N="801.109" TYPE="SECTION">
<HEAD>&#xA7; 801.109 Prescription devices.</HEAD>
<P>(g) A device subject to this paragraph shall bear a label.</P>
<P>(h) The label shall bear the symbol described in this section.</P>
<P>(i) The labeling shall state the conditions of use.</P>
</DIV8>
"""

#: (1) then (i): here the same token *is* a child, and only the sequence says so.
NESTED_I_XML = """<?xml version="1.0"?>
<DIV8 N="820.30" TYPE="SECTION">
<HEAD>&#xA7; 820.30 Design controls.</HEAD>
<P>(a) <I>General.</I> Each manufacturer shall establish procedures.</P>
<P>(1) The procedures shall address the following:</P>
<P>(i) design input requirements;</P>
<P>(ii) design output requirements;</P>
<P>(2) The plans shall be reviewed and approved.</P>
</DIV8>
"""

SUBJGRP_XML = """<?xml version="1.0"?>
<DIV6 N="H" TYPE="SUBPART">
<HEAD>Subpart H&#x2014;Registration</HEAD>
<DIV7 TYPE="SUBJGRP" N="ECFRef316bd359c83c7">
<HEAD>General Provisions</HEAD>
<DIV8 N="1.225" TYPE="SECTION">
<HEAD>&#xA7; 1.225 Who must register.</HEAD>
<P>(a) You must register if you own a facility.</P>
</DIV8>
</DIV7>
</DIV6>
"""


def _parse(xml: str):
    return parse_document(xml.encode(), doc_type=DocType.REGULATION, canonical_key="fda:cfr:21-820")


def _by_path(parsed) -> dict[str, object]:
    return {c.clause_path: c for c in parsed.clauses}


# --- profile selection ----------------------------------------------------------------------


def test_regulation_routes_to_the_cfr_profile() -> None:
    assert profile_for(DocType.REGULATION) == PROFILE == "cfr_structured"


def test_profile_selection_has_no_authority_or_cell_input() -> None:
    """The falsifier ADR-0002 decision 3 sets: selection takes ``doc_type`` and nothing else."""
    import inspect

    from app.parsing import profile_for as selector

    assert list(inspect.signature(selector).parameters) == ["doc_type"]


# --- structure ------------------------------------------------------------------------------


def test_the_part_itself_is_not_a_path_segment() -> None:
    """The Part *is* the Document (ADR-0018 decision 1), so it does not nest inside itself."""
    paths = _by_path(_parse(PART_XML))
    assert "Subpart A/820.35" in paths
    assert not any(p.startswith("820/") for p in paths)


def test_subpart_and_section_nest_the_way_the_adr_specifies() -> None:
    parsed = _parse(PART_XML)
    paths = _by_path(parsed)
    assert paths["Subpart A/820.35"].heading == "§ 820.35 Control of records."
    assert paths["Subpart A/820.35/(a)"].path_segments == ("Subpart A", "820.35", "(a)")
    assert paths["Subpart A/820.35/(a)/(1)"].text.startswith("(1) The name of the device")


def test_the_authority_states_the_citation_and_it_is_read_not_derived() -> None:
    paths = _by_path(_parse(PART_XML))
    assert paths["Subpart A/820.35"].source_ref == "21 CFR 820.35"


def test_range_named_nodes_keep_the_authority_number_verbatim() -> None:
    """Splitting ``820.20-820.30`` into endpoints would invent provisions that do not exist."""
    paths = _by_path(_parse(PART_XML))
    assert "Subpart A/820.20-820.30" in paths
    assert "Subpart C-O" in paths


def test_provenance_is_not_a_clause() -> None:
    """AUTH, SOURCE and CITA state no obligation; admitting them would pollute the denominator."""
    texts = " ".join(c.text for c in _parse(PART_XML).clauses)
    assert "89 FR 7523" not in texts
    assert "21 U.S.C. 351" not in texts
    assert "61 FR 52654" not in texts


def test_an_unlabelled_lead_paragraph_belongs_to_its_section() -> None:
    paths = _by_path(_parse(PART_XML))
    assert "In addition to the requirements" in paths["Subpart A/820.35"].text


def test_inline_markup_is_flattened_into_the_provision_text() -> None:
    """``<I>`` carries a run-in heading — it is part of the quoted provision, not decoration."""
    paths = _by_path(_parse(PART_XML))
    assert "Records of complaints." in paths["Subpart A/820.35/(a)"].text


def test_a_subject_group_never_enters_an_address() -> None:
    """Its identifier is an opaque generated token; a citation built on it would not survive."""
    paths = _by_path(
        parse_document(
            SUBJGRP_XML.encode(), doc_type=DocType.REGULATION, canonical_key="fda:cfr:21-1"
        )
    )
    assert "Subpart H/1.225/(a)" in paths
    assert not any("ECFR" in p for p in paths)


# --- the (i) ambiguity ----------------------------------------------------------------------


def test_i_after_h_is_a_sibling_not_a_child() -> None:
    paths = _by_path(
        parse_document(
            SIBLING_I_XML.encode(), doc_type=DocType.REGULATION, canonical_key="fda:cfr:21-801"
        )
    )
    assert "801.109/(i)" in paths
    assert "801.109/(h)/(i)" not in paths


def test_i_after_a_digit_level_is_a_child() -> None:
    paths = _by_path(
        parse_document(
            NESTED_I_XML.encode(), doc_type=DocType.REGULATION, canonical_key="fda:cfr:21-820"
        )
    )
    assert "820.30/(a)/(1)/(i)" in paths
    assert "820.30/(a)/(1)/(ii)" in paths


def test_a_sibling_after_a_nested_run_closes_the_deeper_levels() -> None:
    paths = _by_path(
        parse_document(
            NESTED_I_XML.encode(), doc_type=DocType.REGULATION, canonical_key="fda:cfr:21-820"
        )
    )
    assert "820.30/(a)/(2)" in paths


def test_parent_index_tracks_the_nesting() -> None:
    parsed = parse_document(
        NESTED_I_XML.encode(), doc_type=DocType.REGULATION, canonical_key="fda:cfr:21-820"
    )
    index = {c.clause_path: n for n, c in enumerate(parsed.clauses)}
    child = parsed.clauses[index["820.30/(a)/(1)/(i)"]]
    assert child.parent_index == index["820.30/(a)/(1)"]


# --- failing closed -------------------------------------------------------------------------


def test_a_non_structural_root_is_drift_not_an_empty_parse() -> None:
    with pytest.raises(ParseError) as caught:
        parse_document(
            b'<?xml version="1.0"?><HTML><BODY>Access Denied</BODY></HTML>',
            doc_type=DocType.REGULATION,
            canonical_key="fda:cfr:21-820",
        )
    assert caught.value.signal is DriftSignal.MISSING_ROOT


def test_a_body_with_no_provisions_is_drift() -> None:
    with pytest.raises(ParseError) as caught:
        parse_document(
            b'<?xml version="1.0"?><DIV5 N="820" TYPE="PART"></DIV5>',
            doc_type=DocType.REGULATION,
            canonical_key="fda:cfr:21-820",
        )
    assert caught.value.signal is DriftSignal.ZERO_CLAUSES


def test_a_section_without_a_number_is_drift() -> None:
    with pytest.raises(ParseError) as caught:
        parse_document(
            b'<?xml version="1.0"?><DIV8 TYPE="SECTION"><P>(a) text</P></DIV8>',
            doc_type=DocType.REGULATION,
            canonical_key="fda:cfr:21-820",
        )
    assert caught.value.signal is DriftSignal.MISSING_ROOT


# --- clause kinds ---------------------------------------------------------------------------


def test_a_subpart_is_a_heading_and_a_provision_is_prose() -> None:
    paths = _by_path(_parse(PART_XML))
    assert paths["Subpart A"].kind is ClauseKind.HEADING
    assert paths["Subpart A/820.35/(a)"].kind is ClauseKind.PROSE
