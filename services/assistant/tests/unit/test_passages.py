"""Passage assembly — ADR-0006 decisions 1 and 2, as falsifiable claims.

Every test here corresponds to a sentence in the ADR that would otherwise be an intention. "Embed
coarse, cite fine" is only true if the 항/호/목 actually roll into their 조 and their paths survive
onto the passage; "annex rows are not embedded" is only true if no row ever produces one.
"""

from __future__ import annotations

from app.passages import ClauseRow, build_passages, is_passage_root
from regops_shared.constants import MAX_PASSAGE_CHARS, ClauseKind, EmbeddingScope


def clause(
    clause_id: str,
    path: str,
    *,
    kind: ClauseKind = ClauseKind.PROSE,
    heading: str | None = None,
    text: str = "",
    ordinal: int = 0,
    parent: str | None = None,
    row_columns: dict | list | None = None,
) -> ClauseRow:
    return ClauseRow(
        id=clause_id,
        clause_path=path,
        kind=kind.value,
        heading=heading,
        text=text,
        ordinal=ordinal,
        parent_clause_id=parent,
        row_columns=row_columns,
    )


def article_tree() -> list[ClauseRow]:
    """A chapter, one article, and the three 항 beneath it."""
    return [
        clause("ch", "제1장", kind=ClauseKind.HEADING, heading="총칙", ordinal=0),
        clause(
            "art",
            "제1장/제8조",
            heading="영업의 금지",
            text="제8조(영업의 금지)",
            ordinal=1,
            parent="ch",
        ),
        clause(
            "p1",
            "제1장/제8조/제1항",
            text="① 누구든지 다음 각 호의 화장품을 판매하여서는 아니 된다.",
            ordinal=2,
            parent="art",
        ),
        clause(
            "p2",
            "제1장/제8조/제2항",
            text="② 제1항을 위반한 자는 등록이 취소된다.",
            ordinal=3,
            parent="art",
        ),
        clause(
            "i1",
            "제1장/제8조/제1항/제1호",
            text="1. 전부 또는 일부가 변패된 화장품",
            ordinal=4,
            parent="p1",
        ),
    ]


def test_article_is_the_passage_root_and_children_roll_in() -> None:
    """The embedding unit is the 조 with its 항/호/목 folded in (decision 1)."""
    passages = build_passages(article_tree(), document_title="화장품법")

    assert len(passages) == 1
    passage = passages[0]
    assert passage.clause_path == "제1장/제8조"
    assert passage.scope is EmbeddingScope.ARTICLE
    for fragment in ("영업의 금지", "아니 된다", "등록이 취소된다", "변패된 화장품"):
        assert fragment in passage.text


def test_child_paths_travel_with_the_passage() -> None:
    """Citation stays finer than retrieval only if the passage names its children."""
    passage = build_passages(article_tree())[0]

    assert passage.child_clause_paths == [
        "제1장/제8조",
        "제1장/제8조/제1항",
        "제1장/제8조/제1항/제1호",
        "제1장/제8조/제2항",
    ]


def test_passage_is_self_describing() -> None:
    """Document title, chapter heading and address. A fragment nobody can place is unretrievable."""
    passage = build_passages(article_tree(), document_title="화장품법")[0]

    assert passage.text.startswith("화장품법 > 총칙\n제1장/제8조")


def test_headings_are_never_passages_of_their_own() -> None:
    """편/장/절 carry no content — embedding them would add vectors that match everything weakly."""
    passages = build_passages(article_tree())

    assert all(passage.clause_path != "제1장" for passage in passages)


def test_annex_table_rows_are_not_embedded() -> None:
    """Decision 2. Thousands of near-identical ingredient lines are the worst index input."""
    rows = [
        clause(
            "t",
            "별표1/표1",
            kind=ClauseKind.TABLE,
            heading="사용할 수 없는 원료",
            row_columns=["원료명", "CAS No."],
            ordinal=0,
        ),
        clause(
            "r1",
            "별표1/표1/행1",
            kind=ClauseKind.TABLE_ROW,
            ordinal=1,
            parent="t",
            row_columns={"원료명": "갈라민트리에치오다이드", "CAS No.": "65-29-2"},
        ),
        clause(
            "r2",
            "별표1/표1/행2",
            kind=ClauseKind.TABLE_ROW,
            ordinal=2,
            parent="t",
            row_columns={"원료명": "갈로타닌산", "CAS No.": "1401-55-4"},
        ),
    ]

    passages = build_passages(rows)

    assert [passage.clause_path for passage in passages] == ["별표1/표1"]
    assert passages[0].scope is EmbeddingScope.TABLE_HEADER


def test_annex_table_header_is_embedded_with_its_column_labels() -> None:
    """So that "화장품에 쓸 수 없는 원료 목록이 있나?" still retrieves the annex."""
    rows = [
        clause(
            "t",
            "별표1/표1",
            kind=ClauseKind.TABLE,
            heading="사용할 수 없는 원료",
            row_columns=["원료명", "CAS No."],
        ),
        clause(
            "r1",
            "별표1/표1/행1",
            kind=ClauseKind.TABLE_ROW,
            ordinal=1,
            parent="t",
            row_columns={"원료명": "갈라민트리에치오다이드"},
        ),
    ]

    passage = build_passages(rows)[0]

    assert "사용할 수 없는 원료" in passage.text
    assert "원료명 | CAS No." in passage.text
    assert "갈라민트리에치오다이드" not in passage.text


def test_prose_inside_an_annex_is_its_own_passage() -> None:
    """Passage roots partition the tree, so annex prose is not folded into the table above."""
    rows = [
        clause("t", "별표1/표1", kind=ClauseKind.TABLE, row_columns=["원료명"]),
        clause(
            "note",
            "별표1/표1/비고",
            text="비고: 위 표의 원료는 화장품에 사용할 수 없다.",
            ordinal=1,
            parent="t",
        ),
    ]

    passages = build_passages(rows)

    assert sorted(passage.clause_path for passage in passages) == ["별표1/표1", "별표1/표1/비고"]
    assert "비고" not in passages[0].text


def test_long_article_splits_at_child_boundaries_keeping_its_heading() -> None:
    """Decision 1: fragments stay self-describing, or they are as useless as a bare 호."""
    filler = "가" * (MAX_PASSAGE_CHARS // 2)
    tree = [
        clause("art", "제9조", heading="안전성 평가", text="제9조(안전성 평가)"),
        clause("p1", "제9조/제1항", text=f"① {filler}", ordinal=1, parent="art"),
        clause("p2", "제9조/제2항", text=f"② {filler}", ordinal=2, parent="art"),
        clause("p3", "제9조/제3항", text=f"③ {filler}", ordinal=3, parent="art"),
    ]

    passages = build_passages(tree, document_title="화장품법")

    assert len(passages) > 1
    assert [passage.fragment_index for passage in passages] == list(range(len(passages)))
    for passage in passages:
        assert passage.scope is EmbeddingScope.ARTICLE_FRAGMENT
        assert "안전성 평가" in passage.text
        assert passage.clause_path == "제9조"


def test_form_is_a_passage_but_carries_no_rows() -> None:
    """A blank 서식 has a title worth retrieving and nothing else worth embedding."""
    passages = build_passages(
        [clause("f", "서식5", kind=ClauseKind.FORM, heading="화장품제조업 변경등록 신청서")]
    )

    assert passages[0].scope is EmbeddingScope.FORM
    assert "화장품제조업 변경등록 신청서" in passages[0].text


def test_no_passage_ever_exceeds_the_cap() -> None:
    """A hard invariant, not a target.

    Ollama answers an over-long embedding request with HTTP 500 rather than truncating, so an
    unbounded passage is not a quality problem — it is a version that never gets indexed. Measured
    on the gated corpus, the shapes that slipped past 항-boundary splitting reached 21,588
    characters.
    """
    giant = "가" * (MAX_PASSAGE_CHARS * 10)
    tree = [
        clause("f", "서식5", kind=ClauseKind.FORM, heading="신청서", text=giant),
        clause("art", "제9조", heading="평가", text=f"제9조(평가) {giant}", ordinal=1),
    ]

    passages = build_passages(tree, document_title="테스트")

    assert passages
    for passage in passages:
        assert len(passage.text) <= MAX_PASSAGE_CHARS


def test_a_cut_fragment_keeps_its_heading_and_a_unique_index() -> None:
    """``(clause_id, fragment_index)`` is UNIQUE, so cutting has to renumber rather than assume."""
    tree = [
        clause(
            "f",
            "서식5",
            kind=ClauseKind.FORM,
            heading="신청서",
            text="\n".join("나" * 200 for _ in range(40)),
        )
    ]

    passages = build_passages(tree, document_title="테스트")

    assert len(passages) > 1
    assert [passage.fragment_index for passage in passages] == list(range(len(passages)))
    for passage in passages:
        assert passage.text.startswith("테스트\n서식5")


def test_a_single_unbreakable_line_is_still_cut() -> None:
    """A box-drawing table renders as one enormous line; refusing to cut it drops the whole page."""
    tree = [clause("t", "별표9/문단1", text="┏" + "━" * (MAX_PASSAGE_CHARS * 4) + "┓")]

    passages = build_passages(tree)

    assert len(passages) > 1
    assert all(len(passage.text) <= MAX_PASSAGE_CHARS for passage in passages)


def test_is_passage_root_rejects_a_nested_paragraph() -> None:
    parent = clause("art", "제8조")
    child = clause("p1", "제8조/제1항", parent="art")

    assert is_passage_root(parent, None)
    assert not is_passage_root(child, parent)


def test_content_hash_changes_with_the_text() -> None:
    """The re-embedding shortcut rests on this: same hash, no inference."""
    first = build_passages(article_tree())[0]
    edited = article_tree()
    edited[2] = clause("p1", "제1장/제8조/제1항", text="① 다른 내용", ordinal=2, parent="art")
    second = build_passages(edited)[0]

    assert first.content_hash != second.content_hash
