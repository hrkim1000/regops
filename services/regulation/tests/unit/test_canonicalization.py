"""Change detection keys on the canonicalized body, never on the raw bytes.

The test that matters most here is :func:`test_view_count_delta_is_not_a_change`. It is a phase 1.0
acceptance criterion and it is the one protecting the detection-coverage gate: if a view counter
reads as an amendment, every poll produces a false positive and coverage becomes unmeasurable.
"""

from __future__ import annotations

import hashlib
import unicodedata

import pytest
from defusedxml.ElementTree import fromstring as parse_xml
from helpers import fixture_text

from app.canonicalize import canonical_records, canonical_xml, is_volatile_field, normalize_text
from app.connectors.mfds import extract_table_rows


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --- the acceptance criterion --------------------------------------------------


def test_view_count_delta_is_not_a_change() -> None:
    """Two MFDS listings differing only in 조회수 must produce the same content_hash."""
    before = extract_table_rows(fixture_text("mfds_listing.html"))
    after = extract_table_rows(fixture_text("mfds_listing_more_views.html"))

    assert before != after, "the fixtures must actually differ, or this test proves nothing"
    assert any("조회수" in row for row in before), "the volatile column must be present pre-drop"
    assert _hash(canonical_records(before)) == _hash(canonical_records(after))


def test_a_real_edit_still_registers() -> None:
    """The counterpart: dropping 조회수 must not make the canonicalizer blind."""
    before = extract_table_rows(fixture_text("mfds_listing.html"))
    amended = [dict(row) for row in before]
    amended[0]["제목"] = amended[0]["제목"] + " (재개정)"

    assert _hash(canonical_records(before)) != _hash(canonical_records(amended))


# --- primitives ----------------------------------------------------------------


@pytest.mark.parametrize(
    "name", ["조회수", "조회 수", "hit", "HITS", "viewCount", "view_count", "read_count"]
)
def test_volatile_fields_recognised(name: str) -> None:
    assert is_volatile_field(name)


@pytest.mark.parametrize("name", ["제목", "제개정일", "구분", "번호", "title"])
def test_content_fields_are_not_volatile(name: str) -> None:
    assert not is_volatile_field(name)


def test_normalize_is_nfc() -> None:
    """The same 한글 syllable arrives precomposed or decomposed depending on the producer; the two
    are byte-different and render identically, so without NFC they would hash as an amendment."""
    precomposed = "화장품"
    decomposed = unicodedata.normalize("NFD", precomposed)
    assert precomposed.encode() != decomposed.encode()
    assert normalize_text(precomposed) == normalize_text(decomposed)


def test_normalize_collapses_incidental_whitespace() -> None:
    assert normalize_text("제1조  \r\n\r\n\r\n제2조   ") == "제1조\n\n제2조"


def test_canonical_xml_ignores_attribute_and_whitespace_noise() -> None:
    """Serialization differences are not content differences."""
    a = parse_xml("<r><a x='1'>text</a><b>more</b></r>")
    b = parse_xml('<r>\n  <a y="2" x="1">text</a>\n  <b>more</b>\n</r>')
    assert canonical_xml(a) == canonical_xml(b)


def test_canonical_xml_records_document_order() -> None:
    """Two clauses swapped IS a change — order is content in a regulation."""
    a = parse_xml("<r><c>first</c><c>second</c></r>")
    b = parse_xml("<r><c>second</c><c>first</c></r>")
    assert canonical_xml(a) != canonical_xml(b)


def test_canonical_xml_drops_requested_subtrees() -> None:
    with_annex = parse_xml("<r><body>text</body><별표><별표내용>x</별표내용></별표></r>")
    without = parse_xml("<r><body>text</body></r>")
    assert canonical_xml(with_annex, drop_tags=("별표",)) == canonical_xml(without)


def test_records_cannot_merge_across_the_boundary() -> None:
    """Two rows must not canonicalize to the same bytes as one concatenated row."""
    two = canonical_records([{"a": "1"}, {"b": "2"}])
    one = canonical_records([{"a": "1", "b": "2"}])
    assert two != one
