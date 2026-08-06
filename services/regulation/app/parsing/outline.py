"""Segmenting free text into a clause tree.

**Why this exists at all:** 법령 본문조회 returns 조문/항/호/목 as separate XML elements, so the
hierarchy is *given*. 행정규칙 본문조회 does not — 화장품 안전기준 등에 관한 규정 comes back as 11
flat ``조문내용`` blobs, one of which is 9,062 characters holding 제6조 with all its 항 and 호 run
together. The clause tree has to be recovered from the text.

That is a **source-shape** difference, not a domain one. Both gated cells have 법령 *and* 고시
sources, so both use both profiles — which is the shared-pipeline claim of ADR-0002 decision 3, and
the reason this segmenter is keyed on nothing but the markers it finds.

Two ladders, because two kinds of document:

``LEGAL``
    The fixed outline 편·장·절·관 → 조 → 항 → 호 → 목. Used for 고시 bodies, where the vocabulary is
    known in advance and chapters must nest by kind (a 절 inside a 장).

``DISCOVERED``
    Depth is assigned by the order in which marker *styles* first appear. Used for annex prose,
    which invents its own outline: 유통화장품 안전관리 시험방법 runs ``Ⅰ.`` → ``1.`` → ``가)`` →
    ``①`` → ``-``, nesting a 항 marker below a 목-like one. No fixed precedence describes that, and
    forcing one collapses the annex into 137 clauses sharing four paths.

    A style already on the stack is a **sibling** — unless it reappears at a deeper indent, which is
    a genuine nested reuse of the same numbering. That combination is what keeps ``2. 니켈`` a
    sibling of ``1. 납`` while ``Ⅱ.`` closes the whole subtree beneath ``Ⅰ.``.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from enum import StrEnum

from regops_shared.constants import ClauseKind

from ..canonicalize import normalize_text
from .markers import CIRCLED_DIGITS, Marker, MarkerStyle, Rank, match_marker
from .model import ParsedClause

#: A 항 marker sitting mid-line rather than at the start of one. 고시 text runs the first 항 onto
#: the article header — ``제6조(유통화장품의 안전관리 기준) ① 유통화장품은 …`` — so without split
#: here the whole article collapses into a single clause and 제6조제1항 is not addressable.
#: Safe to apply unconditionally: a cross-reference to a paragraph is written 제1항, never ①.
_INLINE_PARAGRAPH = re.compile(rf"(?<=\S)\s+(?=[{CIRCLED_DIGITS}])")


class Ladder(StrEnum):
    LEGAL = "legal"
    DISCOVERED = "discovered"


class _Node:
    """One open marker on the stack, accumulating its own text until something closes it."""

    __slots__ = ("index", "lines", "marker", "segment")

    def __init__(self, marker: Marker, index: int, segment: str) -> None:
        self.marker = marker
        self.index = index
        self.segment = segment
        self.lines: list[str] = []


def _logical_lines(lines: list[str]) -> list[str]:
    """Break each physical line before any 항 marker that is not already line-initial."""
    out: list[str] = []
    for line in lines:
        pieces = _INLINE_PARAGRAPH.split(line)
        out.extend(piece for piece in pieces if piece.strip() or len(pieces) == 1)
    return out


def _closes_legal(top: Marker, incoming: Marker) -> bool:
    """Fixed precedence, with chapters compared on ``depth`` as well as rank.

    편/장/절/관 all share ``Rank.CHAPTER``, so rank alone would make 제1절 close the 제2장 that
    contains it.
    """
    if top.rank > incoming.rank:
        return True
    if top.rank < incoming.rank:
        return False
    return top.depth >= incoming.depth


def _close_discovered(
    stack: list[_Node],
    incoming: Marker,
    flush: Callable[[_Node], None],
) -> None:
    """Unwind to the incoming marker's own level.

    A style **already on the stack** is a sibling: unwind past everything above it *and* past the
    matching entry itself, so ``2. 니켈`` closes the ``가) … ① … -`` subtree beneath ``1. 납``. A
    style **not** on the stack opens a new, deeper level and closes nothing — that is the whole
    ladder: depth is first-appearance order.

    The unwind targets the **shallowest** closing entry, not the first one found from the top.
    Stopping at the top-most match leaves intervening levels open (``제1호 / 나목 / 제3호`` where
    ``제3호`` is a sibling of ``제1호`` — how 별표 1 grew to twelve levels), and for dotted
    numbering it would close ``4.1.5`` while leaving ``4.1`` open beneath an incoming ``4.2``.

    **Indentation is deliberately not consulted.** It looks like the obvious signal and it is not:
    annex text is hard-wrapped, and leading whitespace drifts a column or two between lines of the
    same level. Requiring a deeper indent to nest turned ``1.``/``2.`` siblings into a 100-segment
    chain in 의료기기 임상시험 관리기준.
    """
    target = None
    for index, node in enumerate(stack):
        if _closes_discovered(node.marker, incoming):
            target = index
            break
    if target is None:
        return
    while len(stack) > target:
        flush(stack.pop())


def _closes_discovered(top: Marker, incoming: Marker) -> bool:
    """Is ``top`` at or below the incoming marker's own level?

    Same style means same level — except for ISO-style dotted numbering, which carries its own
    depth: ``4.1.1`` nests under ``4.1``, while ``4.2`` closes both.
    """
    if top.style is not incoming.style:
        return False
    if incoming.style is MarkerStyle.DOTTED:
        return top.depth >= incoming.depth
    return True


def segment_outline(
    text: str,
    *,
    prefix: Sequence[str] = (),
    ladder: Ladder = Ladder.LEGAL,
) -> list[ParsedClause]:
    """Segment ``text`` into clauses, each addressed by ``prefix`` plus its marker path.

    ``prefix`` is the address of the container — ``("별표3",)`` for an annex, empty for a 고시 body.

    Line breaks inside a clause are preserved **verbatim**. Annex text is hard-wrapped to a fixed
    page width, and rejoining it means guessing whether a space was absorbed into the padding.
    Guessing wrong silently alters the text of a citable provision. The table parser can afford that
    reconstruction because a cell's width is known; a prose paragraph's is not.
    """
    lines = _logical_lines(normalize_text(text).split("\n"))
    clauses: list[ParsedClause] = []
    stack: list[_Node] = []

    def flush(node: _Node) -> None:
        clauses[node.index].text = normalize_text("\n".join(node.lines))

    for line in lines:
        if not line.strip():
            if stack:
                stack[-1].lines.append("")
            continue

        marker = match_marker(line)
        if marker is None:
            if stack:
                stack[-1].lines.append(line)
            continue

        if ladder is Ladder.DISCOVERED:
            _close_discovered(stack, marker, flush)
        else:
            while stack and _closes_legal(stack[-1].marker, marker):
                flush(stack.pop())

        segments = tuple(prefix) + tuple(node.segment for node in stack if node.segment)
        segment = marker.segment or _bullet_segment(clauses, segments)
        segments += (segment,)

        node = _Node(marker, len(clauses), segment)
        clauses.append(
            ParsedClause(
                path_segments=segments,
                text="",
                kind=ClauseKind.HEADING if marker.rank is Rank.CHAPTER else ClauseKind.PROSE,
                heading=marker.heading,
                parent_index=stack[-1].index if stack else None,
            )
        )
        node.lines.append(line.strip())
        stack.append(node)

    while stack:
        flush(stack.pop())

    return [clause for clause in clauses if clause.text or clause.heading]


def _bullet_segment(clauses: list[ParsedClause], parent: tuple[str, ...]) -> str:
    """A bullet carries no number of its own, so number it among its siblings."""
    siblings = sum(1 for clause in clauses if clause.path_segments[:-1] == parent)
    return f"-{siblings + 1}"


__all__ = ["Ladder", "segment_outline"]
