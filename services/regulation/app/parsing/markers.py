"""The clause-marker vocabulary, and how a marker becomes a path segment.

**This is domain-neutral by construction** (ADR-0002 decision 3). Every marker below is a property
of Korean legal drafting, not of SaMD or Cosmetic — 화장품법 and 의료기기법 use exactly the same
ladder, which is the shared-pipeline claim phase 1.1 exists to test.

Two ladders are needed, and the reason is evidence rather than taste:

- A **statute or 고시 body** uses the fixed legal outline 편·장·절·관 → 조 → 항 → 호 → 목. Its
  precedence is known in advance and is encoded in :class:`Rank`.
- An **annex** is a free-form document that invents its own outline. 유통화장품 안전관리 시험방법
  (별표 4 of 화장품 안전기준 규정) runs ``Ⅰ.`` → ``1.`` → ``가)`` → ``①`` → ``-``, putting a 항
  marker *below* a 목-like one. No fixed precedence describes that, so annex prose discovers its
  ladder from the order in which styles first appear (see :mod:`.outline`).

:class:`MarkerStyle` is what the second ladder keys on: the *style* of a marker, independent of its
value, so ``가)`` and ``나)`` are the same level while ``가.`` and ``가)`` are not.

Vocabulary confirmed against the archived corpus, 2026-08-06: 항번호 is always a circled digit
(①–⑬ observed, 60 unnumbered), 호번호 is ``N.`` or ``N의M.``, 목번호 is the 가나다 sequence.
"""

from __future__ import annotations

import re
from enum import IntEnum, StrEnum
from typing import Final, NamedTuple

#: ① … ⑳ then ㉑ … ㉟. A 항 number is a circled digit in every observed 법령 response, and the
#: rendered segment has to be ``제1항`` rather than ``제①항`` because that is how it is cited.
_CIRCLED: Final[dict[str, int]] = {
    **{chr(0x2460 + i): i + 1 for i in range(20)},  # ①..⑳
    **{chr(0x3251 + i): i + 21 for i in range(15)},  # ㉑..㉟
}

#: The 목 sequence, in order. Restricting to this alphabet is what stops a prose sentence beginning
#: with a single Hangul syllable and a period from being read as a 목 marker.
_MOK_ALPHABET: Final[str] = "가나다라마바사아자차카타파하거너더러머버서어저처커터퍼허"

#: Ⅰ Ⅱ Ⅲ … as single code points, plus the ASCII spelling annexes also use.
_ROMAN: Final[str] = "".join(chr(0x2160 + i) for i in range(12))

CIRCLED_DIGITS: Final[str] = "".join(_CIRCLED)

#: How deeply a 편/장/절/관 nests. A 절 sits inside a 장, so 제1절 of 제2장 and 제1절 of 제3장 are
#: different addresses — flattening them collides, which is what 의료기기법 does three times over.
CHAPTER_DEPTH: Final[dict[str, int]] = {"편": 1, "장": 2, "절": 3, "관": 4}


class Rank(IntEnum):
    """Fixed legal precedence. Lower binds looser: a 장 contains 조, a 조 contains 항.

    Below 목 the Korean convention continues ``1)`` → ``가)``, and 고시 use it heavily — 화장품 안전
    기준 규정 제6조 runs to ``제8항/1)``. Giving the paren styles their own ranks rather than
    reusing ITEM/SUBITEM is what stops ``1)`` from reading as a sibling of ``1.``.
    """

    CHAPTER = 1  # 편 · 장 · 절 · 관
    ARTICLE = 2  # 조
    PARAGRAPH = 3  # 항
    ITEM = 4  # 호        1.
    SUBITEM = 5  # 목      가.
    ITEM_PAREN = 6  # 1)
    SUBITEM_PAREN = 7  # 가)
    BULLET = 8  # - ·


class MarkerStyle(StrEnum):
    """The *shape* of a marker, independent of its value — the key the discovered ladder uses."""

    CHAPTER = "chapter"
    ARTICLE = "article"
    CIRCLED = "circled"  # ①
    DIGIT_DOT = "digit_dot"  # 1.
    DIGIT_PAREN = "digit_paren"  # 1)
    HANGUL_DOT = "hangul_dot"  # 가.
    HANGUL_PAREN = "hangul_paren"  # 가)
    ROMAN_DOT = "roman_dot"  # Ⅰ.
    DOTTED = "dotted"  # 4.1.1 — ISO-style, self-describing depth
    BULLET = "bullet"  # - ·


class Marker(NamedTuple):
    """A recognised marker: where it sits, and how it renders as a path segment."""

    rank: Rank
    segment: str
    #: Text on the same line *after* the marker. The marker itself stays in the clause text — the
    #: authority's own numbering is part of the quoted provision.
    remainder: str
    style: MarkerStyle = MarkerStyle.BULLET
    heading: str | None = None
    #: Nesting depth within :attr:`Rank.CHAPTER`; 1 for anything else.
    depth: int = 1
    #: Leading whitespace of the source line, used by the discovered ladder to tell a nested reuse
    #: of a style from a sibling.
    indent: int = 0


# 제1장 / 제2절 / 제3관 / 제1편, optionally with a 가지번호 (제4장의2).
_CHAPTER = re.compile(r"^제(\d+)(편|장|절|관)(?:의(\d+))?\s*(.*)$")
# 제8조(영업의 종류) / 제2조의2 / 제37조(…) — the heading is optional.
_ARTICLE = re.compile(r"^제(\d+)조(?:의(\d+))?\s*(?:\(([^)]*)\))?\s*(.*)$")
_PARAGRAPH = re.compile(rf"^([{CIRCLED_DIGITS}])\s*(.*)$")
# 4.1 / 4.1.1 / 7.4.2 — ISO 13485's numbering, carried verbatim into 의료기기 제조 및 품질관리 기준.
# Must be tried before the 호 pattern, which would otherwise read "4.1 일반 요구사항" as 제4호 with
# the text "1 일반 요구사항" — and then read 4.1.1 as 제4호 again. That single mis-parse accounted
# for 336 colliding paths in 별표 2 of the GMP 고시.
_DOTTED = re.compile(r"^(\d+(?:\.\d+)+)\.?\s+(.*)$")
# 1. / 2의2. — a 호. The period is required; "1 항목" is prose.
_ITEM = re.compile(r"^(\d+)(?:의(\d+))?\.\s*(.*)$")
_ITEM_PAREN = re.compile(r"^(\d+)(?:의(\d+))?\)\s*(.*)$")
_SUBITEM = re.compile(rf"^([{_MOK_ALPHABET}])\.\s*(.*)$")
_SUBITEM_PAREN = re.compile(rf"^([{_MOK_ALPHABET}])\)\s*(.*)$")
_ROMAN_DOT = re.compile(rf"^([{_ROMAN}]|[IVX]{{1,4}})\.\s*(.*)$")
# A dash or middle-dot bullet, as used inside annex prose.
_BULLET = re.compile(r"^[-–—·ㆍ*○●□■]\s+(.*)$")


def article_segment(number: str, branch: str | None = None) -> str:
    """``("2", "2")`` → ``제2조의2``. The 가지번호 branch is part of the citation, never dropped."""
    base = f"제{number.strip()}조"
    branch = (branch or "").strip().lstrip("0")
    return f"{base}의{branch}" if branch else base


def paragraph_segment(raw: str | None) -> str | None:
    """``①`` → ``제1항``. ``None`` for an unnumbered 항, which contributes **no** segment.

    A 조 with one unnumbered 항 is cited as 제2조제1호, not 제2조제1항제1호 — the implicit 항 is
    not part of the address, so returning ``None`` here is what keeps our paths matching the
    authority's own citations.
    """
    if not raw:
        return None
    value = _CIRCLED.get(raw.strip())
    return f"제{value}항" if value else None


def item_segment(raw: str) -> str:
    """``2의2.`` → ``제2호의2``. The 의-branch renders *after* 호, as citation requires."""
    match = _ITEM.match(raw.strip())
    if not match:
        return f"제{raw.strip().rstrip('.')}호"
    number, branch, _ = match.groups()
    return f"제{number}호의{branch}" if branch else f"제{number}호"


def subitem_segment(raw: str) -> str:
    """``가.`` → ``가목``."""
    return f"{raw.strip().rstrip('.')}목"


def _indent_of(line: str) -> int:
    return len(line) - len(line.lstrip())


def match_marker(line: str) -> Marker | None:
    """Classify one line of free text. ``None`` means it continues the unit above it.

    Order matters: 조 is tried before 호 because ``제1조`` would otherwise never be reached, and the
    bullet is tried last because it is the loosest pattern.

    **호 · 목 · bullet must carry content on their own line.** In fixed-width annex prose a sentence
    ending "…하여야 한다." wraps so that a bare ``다.`` starts the next line, which is
    indistinguishable from a 목 marker by pattern alone. Requiring a remainder rejects the wrap and
    keeps the real 목, which always introduces something. Observed in 의료기기 임상시험 관리기준,
    where it produced two 다목 under one 호.
    """
    stripped = line.strip()
    if not stripped:
        return None
    indent = _indent_of(line)

    def made(rank: Rank, segment: str, rest: str, style: MarkerStyle, **kw: object) -> Marker:
        return Marker(rank, segment, rest, style=style, indent=indent, **kw)  # type: ignore[arg-type]

    if chapter := _CHAPTER.match(stripped):
        number, unit, branch, rest = chapter.groups()
        segment = f"제{number}{unit}" + (f"의{branch}" if branch else "")
        return made(
            Rank.CHAPTER,
            segment,
            rest,
            MarkerStyle.CHAPTER,
            heading=rest.strip() or None,
            depth=CHAPTER_DEPTH[unit],
        )

    if article := _ARTICLE.match(stripped):
        number, branch, heading, rest = article.groups()
        return made(
            Rank.ARTICLE,
            article_segment(number, branch),
            rest,
            MarkerStyle.ARTICLE,
            heading=heading,
        )

    if roman := _ROMAN_DOT.match(stripped):
        mark, rest = roman.groups()
        if rest.strip():
            return made(Rank.ARTICLE, mark, rest, MarkerStyle.ROMAN_DOT)

    if paragraph := _PARAGRAPH.match(stripped):
        mark, rest = paragraph.groups()
        if segment := paragraph_segment(mark):
            return made(Rank.PARAGRAPH, segment, rest, MarkerStyle.CIRCLED)

    if dotted := _DOTTED.match(stripped):
        number, rest = dotted.groups()
        if rest.strip():
            # `depth` is the component count, so 4.1.1 nests under 4.1 rather than closing it.
            return made(Rank.ITEM, number, rest, MarkerStyle.DOTTED, depth=number.count(".") + 1)

    if item := _ITEM.match(stripped):
        number, branch, rest = item.groups()
        if rest.strip():
            segment = f"제{number}호의{branch}" if branch else f"제{number}호"
            return made(Rank.ITEM, segment, rest, MarkerStyle.DIGIT_DOT)

    if item_paren := _ITEM_PAREN.match(stripped):
        number, branch, rest = item_paren.groups()
        if rest.strip():
            segment = f"{number}의{branch})" if branch else f"{number})"
            return made(Rank.ITEM_PAREN, segment, rest, MarkerStyle.DIGIT_PAREN)

    if subitem := _SUBITEM.match(stripped):
        mark, rest = subitem.groups()
        if rest.strip():
            return made(Rank.SUBITEM, subitem_segment(mark), rest, MarkerStyle.HANGUL_DOT)

    if subitem_paren := _SUBITEM_PAREN.match(stripped):
        mark, rest = subitem_paren.groups()
        if rest.strip():
            return made(Rank.SUBITEM_PAREN, f"{mark})", rest, MarkerStyle.HANGUL_PAREN)

    if (bullet := _BULLET.match(stripped)) and bullet.group(1).strip():
        return made(Rank.BULLET, "", bullet.group(1), MarkerStyle.BULLET)

    return None


__all__ = [
    "CHAPTER_DEPTH",
    "CIRCLED_DIGITS",
    "Marker",
    "MarkerStyle",
    "Rank",
    "article_segment",
    "item_segment",
    "match_marker",
    "paragraph_segment",
    "subitem_segment",
]
