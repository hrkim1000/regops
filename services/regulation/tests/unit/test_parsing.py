"""Parser profiles — the clause tree, the table parser, and the dates.

Fixtures here are hand-built from shapes observed in the archived corpus on 2026-08-06, so they
exercise the cases that actually bit rather than the ones that are easy to invent: 목 arriving as a
sibling of 호, a 고시 body with no clause elements at all, a bare ``다.`` produced by hard wrapping,
and a table cell split across a partial rule.
"""

from __future__ import annotations

from datetime import date

import pytest
from defusedxml.ElementTree import fromstring

from app.parsing import ParseError, parse_document, profile_for
from app.parsing.layout import display_width, join_cell, join_wrapped
from app.parsing.markers import MarkerStyle, match_marker
from app.parsing.outline import Ladder, segment_outline
from app.parsing.tables import find_tables, normalize_label
from regops_shared.constants import ClauseKind, DocType, DriftSignal

# --- fixtures ------------------------------------------------------------------------------

LAW_XML = """<?xml version="1.0" encoding="UTF-8"?>
<법령>
  <기본정보>
    <법령ID>002015</법령ID>
    <법종구분>법률</법종구분>
    <법령명_한글>화장품법</법령명_한글>
    <공포일자>20250401</공포일자>
    <시행일자>20260402</시행일자>
  </기본정보>
  <조문>
    <조문단위 조문키="0001000">
      <조문번호>1</조문번호><조문여부>전문</조문여부>
      <조문시행일자>20260402</조문시행일자>
      <조문내용>제1장 총칙</조문내용>
    </조문단위>
    <조문단위 조문키="0002001">
      <조문번호>2</조문번호><조문여부>조문</조문여부><조문제목>정의</조문제목>
      <조문시행일자>20260402</조문시행일자>
      <조문변경여부>Y</조문변경여부>
      <조문내용>제2조(정의) 이 법에서 사용하는 용어의 뜻은 다음과 같다.</조문내용>
      <항>
        <호><호번호>1.</호번호><호내용>1. "화장품"이란 …</호내용></호>
        <호><호번호>2.</호번호><호내용>2. "기능성화장품"이란 …</호내용></호>
        <목><목번호>가.</목번호><목내용>가. 피부의 미백에 도움을 주는 제품</목내용></목>
        <목><목번호>나.</목번호><목내용>나. 피부의 주름개선에 도움을 주는 제품</목내용></목>
        <호><호번호>2의2.</호번호><호내용>2의2. 삭제</호내용></호>
      </항>
    </조문단위>
    <조문단위 조문키="0002021">
      <조문번호>2</조문번호><조문가지번호>2</조문가지번호><조문여부>조문</조문여부>
      <조문제목>영업의 종류</조문제목><조문시행일자>20260402</조문시행일자>
      <조문내용>제2조의2(영업의 종류)</조문내용>
      <항>
        <항번호>①</항번호><항내용>① 이 법에 따른 영업의 종류는 다음 각 호와 같다.</항내용>
        <호><호번호>1.</호번호><호내용>1. 화장품제조업</호내용></호>
      </항>
      <항><항번호>②</항번호><항내용>② 세부 종류는 대통령령으로 정한다.</항내용></항>
    </조문단위>
  </조문>
  <부칙>
    <부칙단위>
      <부칙공포일자>20110804</부칙공포일자>
      <부칙내용>부칙 &lt;제11014호&gt;
제1조(시행일) 이 법은 공포 후 6개월이 경과한 날부터 시행한다.
제2조(경과조치) 종전의 규정에 따른다.</부칙내용>
    </부칙단위>
    <부칙단위>
      <부칙공포일자>20250401</부칙공포일자>
      <부칙내용>부칙 &lt;제20901호&gt;
제1조(시행일) 이 법은 공포 후 1년이 경과한 날부터 시행한다.
다만, 제5조의2의 개정규정은 2028년 1월 1일부터 시행한다.
제2조(경과조치) 생략</부칙내용>
    </부칙단위>
  </부칙>
</법령>
"""

ADMRUL_XML = """<?xml version="1.0" encoding="UTF-8"?>
<AdmRulService>
  <행정규칙기본정보>
    <행정규칙일련번호>37098</행정규칙일련번호>
    <행정규칙명>화장품 안전기준 등에 관한 규정</행정규칙명>
    <발령일자>20260318</발령일자>
    <시행일자>20260318</시행일자>
  </행정규칙기본정보>
  <조문내용>제1장 총칙</조문내용>
  <조문내용>제1조(목적) 이 고시는 화장품법 제8조에 따라 사용기준을 정함을 목적으로 한다.</조문내용>
  <조문내용>제6조(유통화장품의 안전관리 기준) &#x2460; 유통화장품은 기준에 적합하여야 한다.
  &#x2461; 다음 각 호의 검출 허용 한도는 다음과 같다.
  1. 납 : 20㎍/g이하
  2. 니켈: 10㎍/g 이하</조문내용>
  <부칙>
    <부칙단위>
      <부칙공포일자>20260318</부칙공포일자>
      <부칙내용>제1조(시행일) 이 고시는 발령한 날부터 시행한다.</부칙내용>
    </부칙단위>
  </부칙>
</AdmRulService>
"""


def _annex_xml(kind: str, number: str, content: str, *, annex_dates: str = "") -> bytes:
    dates = f"<별표시행일자문자열>{annex_dates}</별표시행일자문자열>" if annex_dates else ""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<AdmRulService>
  <행정규칙기본정보>
    <행정규칙명>테스트 고시</행정규칙명><시행일자>20260318</시행일자>{dates}
  </행정규칙기본정보>
  <조문내용>제1조(목적) 목적.</조문내용>
  <별표>
    <별표단위>
      <별표번호>{number}</별표번호><별표가지번호>00</별표가지번호>
      <별표구분>{kind}</별표구분><별표제목>테스트 {kind}</별표제목>
      <별표내용>{content}</별표내용>
    </별표단위>
  </별표>
</AdmRulService>
""".encode()


TABLE_ANNEX = """[별표 2]

사용상의 제한이 필요한 원료

* 보존제 성분

┌──────────┬─────────┬───────┐
│원    료    명      │사 용 한 도       │CAS No.       │
├──────────┼─────────┼───────┤
│글루타랄(펜탄       │0.1%              │111-30-8      │
│-1,5-디알)          │                  │              │
├──────────┼─────────┼───────┤
│데하이드로아세틱    │0.6%              │16807-48-0 /  │
│애씨드              │                  │520-45-6      │
│                    │                  ├───────┤
│                    │                  │4418-26-2     │
└──────────┴─────────┴───────┘
"""


# --- 법령: hierarchy mode ------------------------------------------------------------------


def test_law_profile_builds_the_chapter_article_paths() -> None:
    parsed = parse_document(LAW_XML.encode(), doc_type=DocType.LAW, canonical_key="mfds:law:002015")
    paths = [clause.clause_path for clause in parsed.clauses]

    assert parsed.profile == "law_structured"
    assert "제1장" in paths
    assert "제1장/제2조" in paths
    # 가지번호 is part of the citation and is never dropped.
    assert "제1장/제2조의2" in paths


def test_mok_attaches_to_the_preceding_ho_not_to_the_hang() -> None:
    """``목`` arrive as *siblings* of ``호`` in the envelope, not as children.

    Reading the tree literally hangs every 목 off the 항 and loses 제2호가목 — the citation an
    answer would actually need.
    """
    parsed = parse_document(LAW_XML.encode(), doc_type=DocType.LAW, canonical_key="mfds:law:002015")
    paths = {clause.clause_path for clause in parsed.clauses}

    assert "제1장/제2조/제2호/가목" in paths
    assert "제1장/제2조/제2호/나목" in paths
    assert "제1장/제2조/가목" not in paths


def test_unnumbered_hang_contributes_no_segment() -> None:
    """화장품법 제2조 has one implicit 항 and is cited 제2조제1호, never 제2조제1항제1호."""
    parsed = parse_document(LAW_XML.encode(), doc_type=DocType.LAW, canonical_key="mfds:law:002015")
    paths = {clause.clause_path for clause in parsed.clauses}

    assert "제1장/제2조/제1호" in paths
    assert "제1장/제2조/제1항/제1호" not in paths
    # A *numbered* 항 does contribute one.
    assert "제1장/제2조의2/제1항/제1호" in paths


def test_ho_branch_number_renders_after_ho() -> None:
    parsed = parse_document(LAW_XML.encode(), doc_type=DocType.LAW, canonical_key="mfds:law:002015")
    assert "제1장/제2조/제2호의2" in {clause.clause_path for clause in parsed.clauses}


def test_law_carries_the_authority_renumber_signal() -> None:
    """``조문키`` and ``조문변경여부`` land on the clause so the diff stage can use a stated move
    rather than inferring one (ADR-0002 decision 7)."""
    parsed = parse_document(LAW_XML.encode(), doc_type=DocType.LAW, canonical_key="mfds:law:002015")
    article = next(c for c in parsed.clauses if c.clause_path == "제1장/제2조")
    assert article.source_ref == "0002001"
    assert article.authority_changed is True


# --- dates ---------------------------------------------------------------------------------


def test_effective_date_comes_from_the_envelope_and_the_phrase_from_the_newest_addendum() -> None:
    """ADR-0016 decision 3–4: the date is authority-stated, the phrase is the 시행일 sentence of the
    **last** 부칙단위 — 화장품법 carries 17 of them and the first describes a 2011 instrument."""
    parsed = parse_document(LAW_XML.encode(), doc_type=DocType.LAW, canonical_key="mfds:law:002015")
    assert parsed.effective_date == date(2026, 4, 2)
    assert parsed.effective_date_phrase is not None
    assert "1년" in parsed.effective_date_phrase
    assert "6개월" not in parsed.effective_date_phrase  # that is the 2011 부칙
    # 경과조치 is not about when the instrument bites.
    assert "경과조치" not in parsed.effective_date_phrase


def test_staged_dates_are_kept_as_a_phrase_not_written_onto_clauses() -> None:
    """ADR-0016 decision 5. 조문시행일자 equals the version's date across the whole gated corpus, so
    writing it onto every clause would fill the column with no information — and the staged date in
    the 부칙 is conditional on the addressee, so it is not a clause-level date at all."""
    parsed = parse_document(LAW_XML.encode(), doc_type=DocType.LAW, canonical_key="mfds:law:002015")
    assert all(clause.effective_date is None for clause in parsed.clauses)
    assert "2028년 1월 1일" in (parsed.effective_date_phrase or "")


# --- 고시: text mode -----------------------------------------------------------------------


def test_admrul_profile_segments_flat_blobs() -> None:
    """행정규칙 본문조회 has no 조문단위 at all — the tree comes out of the text."""
    parsed = parse_document(
        ADMRUL_XML.encode(), doc_type=DocType.NOTICE, canonical_key="mfds:admrul:37098"
    )
    paths = {clause.clause_path for clause in parsed.clauses}

    assert parsed.profile == "admrul_text"
    assert "제1장/제1조" in paths
    assert "제1장/제6조" in paths


def test_admrul_splits_a_paragraph_that_shares_the_article_header_line() -> None:
    """고시 text runs the first 항 onto the article header, so without splitting there the whole
    article collapses into one clause and 제6조제1항 is not addressable."""
    parsed = parse_document(
        ADMRUL_XML.encode(), doc_type=DocType.NOTICE, canonical_key="mfds:admrul:37098"
    )
    paths = {clause.clause_path for clause in parsed.clauses}

    assert "제1장/제6조/제1항" in paths
    assert "제1장/제6조/제2항" in paths
    assert "제1장/제6조/제2항/제1호" in paths


def test_admrul_with_no_clause_markers_raises_drift() -> None:
    """Text with no 제N조 / 항 / 호 numbering is not addressable, so nothing in it is citable."""
    body = """<?xml version="1.0" encoding="UTF-8"?>
<AdmRulService>
  <행정규칙기본정보>
    <행정규칙명>테스트 고시</행정규칙명><시행일자>20260318</시행일자>
  </행정규칙기본정보>
  <조문내용>안내 문구일 뿐 조문 번호가 없는 본문입니다.</조문내용>
</AdmRulService>
"""
    with pytest.raises(ParseError) as excinfo:
        parse_document(body.encode(), doc_type=DocType.NOTICE, canonical_key="mfds:admrul:37098")
    assert excinfo.value.signal is DriftSignal.ZERO_CLAUSES


# --- annexes -------------------------------------------------------------------------------


def test_annex_table_row_is_a_clause_addressable_by_clause_path() -> None:
    """**The phase 1.1 falsifier.** An annex limit-table row must round-trip as a ``Clause`` with
    ``path_segments`` (ADR-0004 decision 3). Failing this falsifies the shared-pipeline claim."""
    parsed = parse_document(
        _annex_xml("별표", "0002", TABLE_ANNEX),
        doc_type=DocType.ANNEX,
        canonical_key="mfds:admrul:37098#별표2",
    )
    rows = [c for c in parsed.clauses if c.kind is ClauseKind.TABLE_ROW]

    assert len(rows) == 2
    assert rows[0].clause_path == "별표2/표1/행1"
    assert rows[0].path_segments == ("별표2", "표1", "행1")
    assert rows[0].row_columns == {
        "원료명": "글루타랄(펜탄-1,5-디알)",
        "사용한도": "0.1%",
        "CAS No.": "111-30-8",
    }


def test_annex_table_clause_carries_the_column_map() -> None:
    """ADR-0014 decision 4: the 표 clause holds the header, each 행 holds its own mapping."""
    parsed = parse_document(
        _annex_xml("별표", "0002", TABLE_ANNEX),
        doc_type=DocType.ANNEX,
        canonical_key="mfds:admrul:37098#별표2",
    )
    table = next(c for c in parsed.clauses if c.kind is ClauseKind.TABLE)
    assert table.clause_path == "별표2/표1"
    assert table.row_columns == ["원료명", "사용한도", "CAS No."]


def test_annex_row_text_is_readable_without_the_column_map() -> None:
    parsed = parse_document(
        _annex_xml("별표", "0002", TABLE_ANNEX),
        doc_type=DocType.ANNEX,
        canonical_key="mfds:admrul:37098#별표2",
    )
    row = next(c for c in parsed.clauses if c.clause_path == "별표2/표1/행1")
    assert "원료명: 글루타랄(펜탄-1,5-디알)" in row.text


def test_a_form_is_one_clause_not_a_table() -> None:
    """197 of 278 annexes are blank 서식/별지. Their box-drawing is layout, and parsing it as data
    would manufacture hundreds of meaningless clauses (ADR-0014 decision 5)."""
    parsed = parse_document(
        _annex_xml("서식", "0001", TABLE_ANNEX),
        doc_type=DocType.ANNEX,
        canonical_key="mfds:admrul:37098#서식1",
    )
    assert len(parsed.clauses) == 1
    assert parsed.clauses[0].kind is ClauseKind.FORM
    assert parsed.clauses[0].clause_path == "서식1"


def test_empty_annex_body_raises_rather_than_being_skipped() -> None:
    """``EMPTY_ANNEX_BODY`` was defined in 1.0 and never raised. An annex silently absent is the
    worst outcome for the cell whose obligations live in them."""
    with pytest.raises(ParseError) as excinfo:
        parse_document(
            _annex_xml("별표", "0009", ""),
            doc_type=DocType.ANNEX,
            canonical_key="mfds:admrul:37098#별표9",
        )
    assert excinfo.value.signal is DriftSignal.EMPTY_ANNEX_BODY


def test_an_annex_takes_its_own_effective_date_where_the_authority_states_one() -> None:
    """``별표시행일자문자열`` is the field ADR-0012's rationale rests on — *"annexes move on their
    own schedule"* — and it lives in 기본정보, not in the 별표단위 it describes.

    An inherited date that happens to be right is not the same as a stated one: it sits in the
    fourth element of the Citation tuple, where being silently wrong is undetectable.
    """
    parsed = parse_document(
        _annex_xml("별표", "0009", TABLE_ANNEX, annex_dates="20260701:별표9,별표10,서식12의2"),
        doc_type=DocType.ANNEX,
        canonical_key="mfds:law:009740#별표9",
    )
    assert parsed.effective_date == date(2026, 7, 1)  # stated, not the parent's 20260318


def test_an_annex_the_amendment_did_not_touch_inherits_its_body_date() -> None:
    """Falling back is correct rather than lazy: an annex absent from the list was not amended, so
    it takes effect with the instrument that carries it."""
    parsed = parse_document(
        _annex_xml("별표", "0001", TABLE_ANNEX, annex_dates="20260701:별표9,별표10"),
        doc_type=DocType.ANNEX,
        canonical_key="mfds:law:009740#별표1",
    )
    assert parsed.effective_date == date(2026, 3, 18)  # the parent's 시행일자


def test_annex_date_string_parses_several_date_groups() -> None:
    """Only single-group values exist in the gated corpus, but the format admits more and a second
    group would otherwise be swallowed into the first group's annex list."""
    from app.parsing.dates import annex_effective_dates

    root = fromstring(
        _annex_xml("별표", "0009", "x", annex_dates="20260701:별표9,별표10;20280101:별표11,서식3")
    )
    assert annex_effective_dates(root) == {
        "별표9": date(2026, 7, 1),
        "별표10": date(2026, 7, 1),
        "별표11": date(2028, 1, 1),
        "서식3": date(2028, 1, 1),
    }


def test_annex_prose_uses_the_discovered_ladder() -> None:
    """An annex invents its own outline; depth follows first-appearance order of marker styles."""
    content = """[별표 3]
인체 세포 배양액 안전기준
1. 용어의 정의
  가. "배양액"이란 …
  나. "공여자"란 …
2. 일반사항
  가. 누구든지 …
"""
    parsed = parse_document(
        _annex_xml("별표", "0003", content),
        doc_type=DocType.ANNEX,
        canonical_key="mfds:admrul:37098#별표3",
    )
    paths = {clause.clause_path for clause in parsed.clauses}

    assert "별표3/제1호/가목" in paths
    assert "별표3/제2호/가목" in paths
    assert "별표3/서문" in paths  # the title block is kept, not dropped


# --- the layout reconstruction ---------------------------------------------------------------


def test_display_width_counts_hangul_as_two_columns() -> None:
    assert display_width("원료명") == 6
    assert display_width("CAS") == 3


@pytest.mark.parametrize(
    ("fragments", "expected"),
    [
        # Forced mid-word wrap after Hangul — no space was lost.
        (["글루타랄(펜탄       ", "-1,5-디알)          "], "글루타랄(펜탄-1,5-디알)"),
        (["에어로졸(스프레   ", "이에 한함)        "], "에어로졸(스프레이에 한함)"),
        # Voluntary break — the next token would have fitted, so a space is restored.
        (["이에 한함)        ", "제품에는          "], "이에 한함) 제품에는"),
        # Forced break after a non-Hangul run: a solidus cannot end a token mid-word, so the
        # space the padding swallowed is restored.
        (["16807-48-0 /  ", "520-45-6      "], "16807-48-0 / 520-45-6"),
    ],
)
def test_join_wrapped_reconstructs_fixed_width_cells(fragments: list[str], expected: str) -> None:
    assert join_wrapped(fragments) == expected


def test_join_cell_treats_a_sub_row_rule_as_a_hard_break() -> None:
    """A partial rule inside a row is a boundary the authority drew — two CAS numbers against one
    원료명 — so it becomes a newline rather than being run together."""
    assert join_cell(["16807-48-0 /  ", "520-45-6      ", None, "4418-26-2     "]) == (
        "16807-48-0 / 520-45-6\n4418-26-2"
    )


def test_normalize_label_strips_justification_spacing_but_keeps_latin_spaces() -> None:
    assert normalize_label("원    료    명") == "원료명"
    assert normalize_label("사 용 한 도") == "사용한도"
    assert normalize_label("CAS No.") == "CAS No."


def test_a_logical_row_spans_several_physical_lines() -> None:
    """Rows are delimited by ``├──┼──┤`` rules, not by newlines. Counting lines overstates the row
    count by roughly 16× — the mistake behind "tens of thousands of rows per 고시"."""
    tables = find_tables(TABLE_ANNEX)
    assert len(tables) == 1
    assert len(tables[0].rows) == 2  # not the 6 physical content lines


# --- markers -------------------------------------------------------------------------------


def test_a_bare_marker_is_a_wrapped_sentence_not_a_subitem() -> None:
    """Fixed-width wrapping puts "…하여야 한" / "다." on two lines, and a bare ``다.`` is
    indistinguishable from a 목 marker by pattern alone."""
    assert match_marker("  다.") is None
    assert match_marker("  다. 실제 목입니다") is not None


def test_dotted_decimal_is_its_own_style() -> None:
    """ISO 13485 numbering carried into the GMP 고시. Read as a 호, ``4.1`` and ``4.1.1`` become
    제4호 and collide — 336 times in 별표 2 alone."""
    marker = match_marker("4.1.1 조직은 문서화하여야 한다")
    assert marker is not None
    assert marker.style is MarkerStyle.DOTTED
    assert marker.segment == "4.1.1"
    assert marker.depth == 3


def test_discovered_ladder_nests_dotted_numbering_by_its_own_depth() -> None:
    clauses = segment_outline(
        "4.1 일반 요구사항\n4.1.1 조직은 …\n4.1.2 조직은 …\n4.2 문서화 요구사항\n",
        prefix=("별표2",),
        ladder=Ladder.DISCOVERED,
    )
    paths = [clause.clause_path for clause in clauses]
    assert paths == ["별표2/4.1", "별표2/4.1/4.1.1", "별표2/4.1/4.1.2", "별표2/4.2"]


def test_discovered_ladder_treats_a_seen_style_as_a_sibling() -> None:
    """``2.`` closes the whole ``가) … ①`` subtree beneath ``1.`` rather than nesting under it."""
    clauses = segment_outline(
        "Ⅰ. 일반화장품\n1. 납\n 가) 디티존법\n  ① 검액\n 나) 원자흡광\n2. 니켈\n",
        prefix=("별표4",),
        ladder=Ladder.DISCOVERED,
    )
    paths = [clause.clause_path for clause in clauses]
    assert "별표4/Ⅰ/제1호/가)/제1항" in paths
    assert "별표4/Ⅰ/제2호" in paths  # sibling of 제1호, not nested under 나)


def test_legal_ladder_nests_sections_inside_chapters() -> None:
    """편/장/절/관 share a rank, so rank alone would let 제1절 close the 제2장 containing it — and
    의료기기법 has 제1절 in three different 장."""
    clauses = segment_outline(
        "제1장 총칙\n제1조(목적) 목적.\n제2장 영업\n제1절 기준\n제5조(기준) 기준.\n"
    )
    paths = [clause.clause_path for clause in clauses]
    assert "제2장/제1절/제5조" in paths


# --- routing -------------------------------------------------------------------------------


def test_profiles_are_selected_by_document_shape_not_by_domain() -> None:
    """The falsifier's negative half: no profile is keyed on SaMD vs Cosmetic. 화장품법 and
    의료기기법 are both ``law``, so both take the same profile."""
    assert profile_for(DocType.LAW) == "law_structured"
    assert profile_for(DocType.DECREE) == "law_structured"
    assert profile_for(DocType.ENFORCEMENT_RULE) == "law_structured"
    assert profile_for(DocType.NOTICE) == "admrul_text"
    assert profile_for(DocType.ANNEX) == "annex"


def test_a_malformed_body_is_drift_not_content() -> None:
    with pytest.raises(ParseError) as excinfo:
        parse_document(b"<html><body>error", doc_type=DocType.LAW, canonical_key="mfds:law:002015")
    assert excinfo.value.signal is DriftSignal.MISSING_ROOT


def test_an_error_page_fails_closed_even_though_it_is_well_formed() -> None:
    """``lawService.do?target=eflaw`` answers HTTP 500 with an XHTML page, and that page **parses**
    — it is well-formed. So the XML gate does not catch it and the clause gate has to: no 조문단위,
    therefore ``zero_clauses``, therefore no version and no change event (ADR-0016 decision 2).

    Worth an explicit test because "it isn't XML" is the intuitive defence and it is not the one
    that fires."""
    error_page = (
        b'<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml">'
        b"<head><title>500</title></head><body>error</body></html>"
    )
    with pytest.raises(ParseError) as excinfo:
        parse_document(error_page, doc_type=DocType.LAW, canonical_key="mfds:law:002015")
    assert excinfo.value.signal is DriftSignal.ZERO_CLAUSES


def test_clause_paths_are_unique_within_a_version() -> None:
    """The unique constraint is a hard one, and free-form annex outlines do repeat their numbering.
    A repeat is disambiguated deterministically rather than dropping the clause."""
    content = "1. 첫 번째 절\n  가. 내용\n2. 두 번째 절\n1. 다시 첫 번째\n  가. 내용\n"
    parsed = parse_document(
        _annex_xml("별표", "0005", content),
        doc_type=DocType.ANNEX,
        canonical_key="mfds:admrul:37098#별표5",
    )
    paths = [clause.clause_path for clause in parsed.clauses]
    assert len(paths) == len(set(paths))
    assert any("~2" in path for path in paths)


def test_parse_is_deterministic() -> None:
    """Re-parsing the same bytes must give the same addresses, or a stored citation stops
    resolving after a re-run."""
    first = parse_document(LAW_XML.encode(), doc_type=DocType.LAW, canonical_key="mfds:law:002015")
    second = parse_document(LAW_XML.encode(), doc_type=DocType.LAW, canonical_key="mfds:law:002015")
    assert [c.clause_path for c in first.clauses] == [c.clause_path for c in second.clauses]
    assert [c.content_hash for c in first.clauses] == [c.content_hash for c in second.clauses]


def test_no_clause_field_is_domain_specific() -> None:
    """A column only one domain populates is a falsifier trigger, not a schema detail. Guarding it
    here keeps the check in CI rather than in a diff review."""
    from regops_shared.models import Clause

    forbidden = {"samd", "cosmetic", "domain", "device", "ingredient", "substance", "cas"}
    columns = {column.name.lower() for column in Clause.__table__.columns}
    assert not (columns & forbidden), f"domain-specific column on clauses: {columns & forbidden}"


def test_xml_fixture_matches_the_archived_envelope_shape() -> None:
    """Guards the fixtures themselves: if the real envelope stops looking like this, the unit tests
    would keep passing against a shape that no longer exists."""
    root = fromstring(LAW_XML.encode())
    assert root.tag == "법령"
    assert len(list(root.iter("조문단위"))) == 3
    # 목 really are siblings of 호, which is the whole point of the parser's flat walk.
    article = list(root.iter("조문단위"))[1]
    hang = next(iter(article.iter("항")))
    assert [child.tag for child in hang] == ["호", "호", "목", "목", "호"]
