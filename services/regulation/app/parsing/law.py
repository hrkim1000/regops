"""법령 profile — hierarchy mode over the structured envelope.

국가법령정보 본문조회 returns 조문/항/호/목 as **separate XML elements**, so ADR-0002 decision 3's
clause hierarchy is *given* rather than inferred. This profile's whole job is turning that tree into
paths, and two details of the envelope make it less mechanical than it looks:

1. **``목`` are siblings of ``호``, not children of them.** Inside ``<항>`` the API emits a flat
   sequence — 호, 호, 목, 목, 목, 호 — in document order. A 목 belongs to the most recent preceding
   호, and reading the tree literally would hang every 목 off the 항 and lose 제2호가목 entirely.
2. **``조문여부`` distinguishes 전문 from 조문.** The 전문 rows are 편/장/절/관 headings, and they
   carry the chapter context every following article's path needs (``제2장/제8조/…``).

The authority also publishes the renumbering signal here — ``조문이동이전``, ``조문이동이후`` and
``조문변경여부`` per 조 — which is why those land on the clause rather than being inferred by the
diff stage (ADR-0002 decision 7).
"""

from __future__ import annotations

from datetime import date
from xml.etree.ElementTree import Element

from regops_shared.constants import ClauseKind, DriftSignal

from ..canonicalize import normalize_text
from .dates import (
    clause_effective_date,
    enforcement_phrase,
    envelope_effective_date,
)
from .markers import (
    Rank,
    article_segment,
    item_segment,
    match_marker,
    paragraph_segment,
    subitem_segment,
)
from .model import ParsedClause, ParsedDocument, ParseError

PROFILE = "law_structured"

#: This profile takes a parsed XML root, not the archived bytes. See :mod:`.` .
ACCEPTS_RAW = False


def parse(root: Element) -> ParsedDocument:
    """Parse a 법령 본문조회 envelope into a clause tree."""
    version_date = envelope_effective_date(root)
    document = ParsedDocument(
        profile=PROFILE,
        effective_date=version_date,
        effective_date_phrase=enforcement_phrase(root),
    )

    units = list(root.iter("조문단위"))
    if not units:
        raise ParseError(
            "법령 response carried no 조문단위 — the envelope changed or the body is empty",
            signal=DriftSignal.ZERO_CLAUSES,
            expected="at least one 조문단위",
        )

    # 편 > 장 > 절 > 관 nest. 의료기기법 has 제1절 inside three different 장, so a flat chapter
    # segment collides three times and two of the sections lose their identity.
    stack: list[tuple[int, str, int]] = []

    for unit in units:
        if _is_chapter(unit):
            _chapter(unit, document, stack)
            continue

        _article(
            unit,
            document,
            chapter=tuple(segment for _, segment, _ in stack),
            parent=stack[-1][2] if stack else None,
            version_date=version_date,
        )

    return document


def _chapter(unit: Element, document: ParsedDocument, stack: list[tuple[int, str, int]]) -> None:
    """Push a 편/장/절/관 heading, closing any sibling or deeper level first."""
    text = normalize_text(unit.findtext("조문내용") or "")
    if not text:
        return
    marker = match_marker(text)
    if marker is None or marker.rank is not Rank.CHAPTER:
        return

    while stack and stack[-1][0] >= marker.depth:
        stack.pop()

    segments = (*(segment for _, segment, _ in stack), marker.segment)
    document.clauses.append(
        ParsedClause(
            path_segments=segments,
            text=text,
            kind=ClauseKind.HEADING,
            heading=marker.heading or text,
            source_ref=unit.get("조문키"),
            parent_index=stack[-1][2] if stack else None,
        )
    )
    stack.append((marker.depth, marker.segment, len(document.clauses) - 1))


def _is_chapter(unit: Element) -> bool:
    return normalize_text(unit.findtext("조문여부") or "") == "전문"


def _article(
    unit: Element,
    document: ParsedDocument,
    *,
    chapter: tuple[str, ...],
    parent: int | None,
    version_date: date | None,
) -> None:
    number = normalize_text(unit.findtext("조문번호") or "")
    if not number:
        return
    branch = normalize_text(unit.findtext("조문가지번호") or "")
    segments = (*chapter, article_segment(number, branch))

    article_index = len(document.clauses)
    document.clauses.append(
        ParsedClause(
            path_segments=segments,
            text=normalize_text(unit.findtext("조문내용") or ""),
            kind=ClauseKind.PROSE,
            heading=normalize_text(unit.findtext("조문제목") or "") or None,
            effective_date=clause_effective_date(unit.findtext("조문시행일자"), version_date),
            source_ref=unit.get("조문키"),
            moved_from_ref=_ref(unit, "조문이동이전"),
            moved_to_ref=_ref(unit, "조문이동이후"),
            authority_changed=_flag(unit, "조문변경여부"),
            parent_index=parent,
        )
    )

    for paragraph in unit.iter("항"):
        _paragraph(paragraph, document, prefix=segments, parent=article_index)


def _paragraph(
    element: Element,
    document: ParsedDocument,
    *,
    prefix: tuple[str, ...],
    parent: int,
) -> None:
    """One ``<항>`` and the flat 호/목 sequence beneath it.

    An **unnumbered** 항 contributes no segment: 화장품법 제2조 has one implicit 항 and is cited
    as 제2조제1호, not 제2조제1항제1호. Emitting a phantom 제1항 would make every such citation
    disagree with the authority's own — so the 호 below it attach straight to the 조.
    """
    if segment := paragraph_segment(element.findtext("항번호")):
        prefix = (*prefix, segment)
        document.clauses.append(
            ParsedClause(
                path_segments=prefix,
                text=normalize_text(element.findtext("항내용") or ""),
                kind=ClauseKind.PROSE,
                parent_index=parent,
            )
        )
        parent = len(document.clauses) - 1

    # 호 and 목 arrive as *siblings* in document order, not nested: a 목 belongs to the most recent
    # preceding 호. Reading the tree literally would hang every 목 off the 항 and lose 제2호가목.
    item_prefix = prefix
    item_parent = parent
    for child in element:
        if child.tag == "호":
            item_prefix = (*prefix, item_segment(normalize_text(child.findtext("호번호") or "")))
            document.clauses.append(
                ParsedClause(
                    path_segments=item_prefix,
                    text=normalize_text(child.findtext("호내용") or ""),
                    kind=ClauseKind.PROSE,
                    parent_index=parent,
                )
            )
            item_parent = len(document.clauses) - 1
        elif child.tag == "목":
            document.clauses.append(
                ParsedClause(
                    path_segments=(
                        *item_prefix,
                        subitem_segment(normalize_text(child.findtext("목번호") or "")),
                    ),
                    text=normalize_text(child.findtext("목내용") or ""),
                    kind=ClauseKind.PROSE,
                    parent_index=item_parent,
                )
            )


def _ref(unit: Element, tag: str) -> str | None:
    """A move reference, treating the authority's ``000000`` filler as absent."""
    value = normalize_text(unit.findtext(tag) or "")
    return value if value and set(value) != {"0"} else None


def _flag(unit: Element, tag: str) -> bool | None:
    value = normalize_text(unit.findtext(tag) or "")
    return {"Y": True, "N": False}.get(value)


__all__ = ["PROFILE", "parse"]
