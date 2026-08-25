"""``cfr_structured`` — eCFR XML, the fourth profile.

Selected by ``doc_type`` like the other three (:data:`DocType.REGULATION`), never by authority or
cell. A CFR Part and a 법령 take different profiles because their *envelopes* differ, which is the
same reason 고시 and 별표 take their own — ADR-0002 decision 3.

**What differs from ``law_structured``, and it is the expensive part.** 국가법령정보 hands over
조/항/호/목 as separate XML elements, so ``law`` has no segmentation to do. The eCFR hands over a
flat run of ``<P>`` elements whose paragraph designators — ``(a)``, ``(1)``, ``(i)``, ``(A)`` — are
**inline prose at the head of the text**. The hierarchy has to be recovered from the sequence of
those designators, which is what most of this module is.

**Addressing.** ``path_segments`` is ``[subpart, section, paragraph…]``
([ADR-0018](../../../../docs/design/ADR-0018-fda-source-model.md) decision 1), so a clause stores
``Subpart B/820.35/(a)/(1)``. The rendered citation a US regulatory professional writes —
``21 CFR 820.35(a)(1)`` — is composed at citation time from the Document's ``canonical_key`` plus
this path, exactly as MFDS stores ``제7장/제43조/제1항`` while a lawyer writes 화장품법 제43조제1항.
ADR-0018 decision 1 gives the rendered form as its example; this is the stored form of the same
address, not a departure from it.

**What is deliberately not a clause.** ``<AUTH>`` (statutory authority) and ``<SOURCE>`` /
``<CITA>`` (Federal Register amendment history) are provenance about the instrument, not provisions
of it. They state no obligation, and admitting them would put "89 FR 7523, Feb. 2, 2024" into the
extraction denominator as though it were regulatory text.
"""

from __future__ import annotations

import re
from typing import Final
from xml.etree.ElementTree import Element

from regops_shared.constants import ClauseKind, DriftSignal

from ..canonicalize import normalize_text
from .model import ParsedClause, ParsedDocument, ParseError

PROFILE = "cfr_structured"

#: ``TYPE`` attribute → how deep the node sits. The eCFR numbers its ``DIV`` elements by depth
#: (DIV5 part, DIV6 subpart, DIV8 section) but the ``TYPE`` is what actually names the level, and
#: title 21 contains at least one node type — ``SUBJGRP`` — that carries no number of its own.
_CONTAINER_TYPES: Final[frozenset[str]] = frozenset(
    {"TITLE", "CHAPTER", "SUBCHAP", "PART", "SUBPART", "SUBJGRP", "APPENDIX"}
)

#: Nodes that hold provisions rather than contain other nodes.
_LEAF_TYPES: Final[frozenset[str]] = frozenset({"SECTION"})

#: Provenance elements — skipped, never turned into clauses. See the module docstring.
_PROVENANCE_TAGS: Final[frozenset[str]] = frozenset({"AUTH", "SOURCE", "CITA", "EDNOTE", "EFFDNOT"})

#: A paragraph designator at the head of a ``<P>``: ``(a)``, ``(1)``, ``(iv)``, ``(A)``.
_DESIGNATOR = re.compile(r"^\(([A-Za-z]{1,5}|\d{1,3})\)\s*")

_ROMAN_VALUES: Final[dict[str, int]] = {
    "i": 1,
    "v": 5,
    "x": 10,
    "l": 50,
    "c": 100,
    "d": 500,
    "m": 1000,
}


class _Style:
    """The four designator alphabets, in the order the CFR nests them."""

    LOWER_ALPHA = "lower_alpha"  # (a)
    DIGIT = "digit"  # (1)
    LOWER_ROMAN = "lower_roman"  # (i)
    UPPER_ALPHA = "upper_alpha"  # (A)


#: The CFR ladder repeats after four levels: (a)(1)(i)(A)(1)(i)…
_LADDER: Final[tuple[str, ...]] = (
    _Style.LOWER_ALPHA,
    _Style.DIGIT,
    _Style.LOWER_ROMAN,
    _Style.UPPER_ALPHA,
    _Style.DIGIT,
    _Style.LOWER_ROMAN,
)


def _roman_to_int(token: str) -> int | None:
    """``iv`` → 4. ``None`` when the token is not well-formed roman."""
    total = previous = 0
    for char in reversed(token):
        value = _ROMAN_VALUES.get(char)
        if value is None:
            return None
        total += -value if value < previous else value
        previous = max(previous, value)
    return total or None


def _alpha_to_int(token: str) -> int | None:
    """``a`` → 1, ``aa`` → 27, the way the CFR continues past ``z``."""
    if not token.isalpha():
        return None
    total = 0
    for char in token.lower():
        total = total * 26 + (ord(char) - ord("a") + 1)
    return total


def _successor_of(token: str, style: str, previous: str | None) -> bool:
    """Is ``token`` the next label after ``previous`` in ``style``?

    This is what disambiguates ``(i)``. It is both the ninth lowercase letter and roman one, and the
    CFR uses both — ``(h)`` is followed by ``(i)`` as a *sibling*, while a ``(1)`` level is followed
    by ``(i)`` as a *child*. Style alone cannot tell them apart; position in the sequence can.
    """
    if previous is None:
        return _index_in(token, style) == 1
    prior = _index_in(previous, style)
    current = _index_in(token, style)
    return prior is not None and current == prior + 1


def _index_in(token: str, style: str) -> int | None:
    if style == _Style.DIGIT:
        return int(token) if token.isdigit() else None
    if style == _Style.LOWER_ROMAN:
        return _roman_to_int(token) if token.islower() else None
    if style == _Style.LOWER_ALPHA:
        return _alpha_to_int(token) if token.isalpha() and token.islower() else None
    if style == _Style.UPPER_ALPHA:
        return _alpha_to_int(token) if token.isalpha() and token.isupper() else None
    return None


def _element_text(node: Element) -> str:
    """Flatten inline markup. ``<I>`` run-in headings are part of the provision's text."""
    return normalize_text("".join(node.itertext()))


def _citation_of(node: Element) -> str | None:
    """The citation the authority states on the node, from ``hierarchy_metadata``.

    Read rather than derived — ADR-0018 decision 2. Returned for provenance and for cross-checking
    the number we address by; the address itself still comes from ``N`` so that a missing or
    reshaped metadata attribute degrades to "no cross-check" instead of "no clause".
    """
    raw = node.get("hierarchy_metadata")
    if not raw:
        return None
    match = re.search(r'"citation"\s*:\s*"([^"]+)"', raw.replace("&quot;", '"'))
    return match.group(1) if match else None


def _style_at(depth: int) -> str:
    return _LADDER[depth] if depth < len(_LADDER) else _LADDER[-1]


def _depth_for(token: str, stack: list[tuple[str, str, int]]) -> int:
    """Which level does this designator belong to — an open one, or a new child?

    Walking the open levels from the inside out is the whole disambiguation. ``(i)`` after ``(h)``
    finds a level whose last label was ``h`` and continues it; ``(i)`` after ``(1)`` finds no level
    that it continues, so it opens a child, which the ladder types as roman.
    """
    for depth in range(len(stack) - 1, -1, -1):
        label, style, _ = stack[depth]
        if _successor_of(token, style, label.strip("()")):
            return depth

    child_depth = len(stack)
    if _index_in(token, _style_at(child_depth)) == 1:
        return child_depth

    # Neither a successor nor a well-formed first child — the authority's sequence broke. Address it
    # at the level whose alphabet it does match, so an unexpected designator costs its nesting
    # rather than the provision.
    for depth in range(len(stack), -1, -1):
        if _index_in(token, _style_at(depth)) is not None:
            return depth
    return child_depth


def _append_unlabelled(
    text: str,
    *,
    prefix: tuple[str, ...],
    stack: list[tuple[str, str, int]],
    clauses: list[ParsedClause],
) -> None:
    """An undesignated ``<P>`` continues whatever is open, or is the section's own lead text."""
    if stack:
        index = stack[-1][2]
        clauses[index].text = normalize_text(f"{clauses[index].text}\n{text}")
        return
    if clauses and clauses[-1].path_segments == prefix:
        clauses[-1].text = normalize_text(f"{clauses[-1].text}\n{text}")
        return
    clauses.append(ParsedClause(path_segments=prefix, text=text, kind=ClauseKind.PROSE))


def _segment_paragraphs(
    paragraphs: list[str], *, prefix: tuple[str, ...], clauses: list[ParsedClause]
) -> None:
    """Turn a flat run of ``<P>`` texts into a nested clause tree, by designator sequence.

    The rule is **sequence first, style second**. For each designator the walker asks, from the
    deepest open level outward, "is this the next label here?" — and only when no open level claims
    it does it open a child. That ordering is what makes ``(h)`` → ``(i)`` a pair of siblings while
    ``(1)`` → ``(i)`` is a parent and its child, with neither case needing to be special-cased.

    A ``<P>`` with no designator is not an error: a section commonly opens with an unlabelled
    paragraph, and 820.35 does.
    """
    #: (path segment, style, index into ``clauses``) per open level, outermost first.
    stack: list[tuple[str, str, int]] = []

    for text in paragraphs:
        match = _DESIGNATOR.match(text)
        if match is None:
            _append_unlabelled(text, prefix=prefix, stack=stack, clauses=clauses)
            continue

        token = match.group(1)
        depth = _depth_for(token, stack)
        del stack[depth:]

        segment = f"({token})"
        parent_index = stack[-1][2] if stack else None
        clauses.append(
            ParsedClause(
                path_segments=(*prefix, *(level[0] for level in stack), segment),
                text=text,
                kind=ClauseKind.PROSE,
                parent_index=parent_index,
            )
        )
        stack.append((segment, _style_at(len(stack)), len(clauses) - 1))


def _container_segment(node_type: str, number: str | None) -> str:
    """How a container renders in a path.

    ``N`` is kept **verbatim**, which is what carries the range-named nodes the QMSR left behind —
    subpart ``C-O`` and section ``820.20-820.30`` are single nodes whose number is a range, and
    splitting either into endpoints would invent provisions that do not exist (ADR-0018 decision 2).
    """
    if node_type == "PART":
        return ""  # the Part *is* the Document; it is not a segment inside itself.
    if node_type == "SUBJGRP":
        # Its ``N`` is an opaque generated token (``ECFRef316bd359c83c7``) that the authority may
        # regenerate. A citation addressed through it would not survive, so a subject group groups
        # in the source and disappears from the address — the sections keep their own numbers.
        return ""
    if not number:
        return ""
    if node_type == "SUBPART":
        return f"Subpart {number}"
    return number  # APPENDIX numbers are already prose: "Appendix B to Part 101".


def _first_text(node: Element, tag: str) -> str | None:
    child = node.find(tag)
    return _element_text(child) if child is not None else None


def _section(
    node: Element,
    *,
    prefix: tuple[str, ...],
    clauses: list[ParsedClause],
    parent_index: int | None,
) -> None:
    number = node.get("N")
    if not number:
        raise ParseError(
            "a SECTION node carries no N attribute",
            signal=DriftSignal.MISSING_ROOT,
            expected='<DIV8 TYPE="SECTION" N="820.35">',
        )
    heading = _first_text(node, "HEAD")
    section_prefix = (*prefix, number)
    clauses.append(
        ParsedClause(
            path_segments=section_prefix,
            text=heading or number,
            kind=ClauseKind.PROSE,
            heading=heading,
            parent_index=parent_index,
            source_ref=_citation_of(node),
        )
    )
    paragraphs = [text for child in node if child.tag == "P" and (text := _element_text(child))]
    _segment_paragraphs(paragraphs, prefix=section_prefix, clauses=clauses)


def _walk(
    node: Element,
    *,
    prefix: tuple[str, ...],
    clauses: list[ParsedClause],
    parent_index: int | None = None,
) -> None:
    """Recurse the ``DIV`` tree, emitting a clause per container and per section."""
    node_type = (node.get("TYPE") or "").upper()

    if node_type in _LEAF_TYPES:
        _section(node, prefix=prefix, clauses=clauses, parent_index=parent_index)
        return
    if node_type not in _CONTAINER_TYPES:
        return

    segment = _container_segment(node_type, node.get("N"))
    child_prefix = (*prefix, segment) if segment else prefix
    index = parent_index

    if segment:
        heading = _first_text(node, "HEAD")
        clauses.append(
            ParsedClause(
                path_segments=child_prefix,
                text=heading or segment,
                kind=ClauseKind.HEADING,
                heading=heading,
                parent_index=parent_index,
                source_ref=_citation_of(node),
            )
        )
        index = len(clauses) - 1

    for child in node:
        if child.tag == "HEAD" or child.tag in _PROVENANCE_TAGS:
            continue
        _walk(child, prefix=child_prefix, clauses=clauses, parent_index=index)


def parse(root: Element) -> ParsedDocument:
    """eCFR XML → clauses.

    The root is whatever granularity was fetched: a ``PART`` for a whole-Part fetch, a ``SUBPART``
    or a ``SECTION`` for a narrower one. All three are valid entry points because the eCFR serves
    all three from one endpoint, and a profile that accepted only Parts would turn the fetch
    granularity into a parsing decision.

    ``effective_date`` is **not** read here. For this authority it comes from the Federal Register's
    ``effective_on`` at version level (ADR-0018 decision 5), never from the body — there is no 부칙
    to parse and nothing in the XML states it.
    """
    node_type = (root.get("TYPE") or "").upper()
    if node_type not in _CONTAINER_TYPES | _LEAF_TYPES:
        raise ParseError(
            f"root node TYPE {node_type!r} is not a CFR structural node",
            signal=DriftSignal.MISSING_ROOT,
            expected="a DIV with TYPE of PART, SUBPART, SUBJGRP, APPENDIX or SECTION",
        )

    clauses: list[ParsedClause] = []
    _walk(root, prefix=(), clauses=clauses)

    if not clauses:
        raise ParseError(
            "no clauses were produced from the CFR body",
            signal=DriftSignal.ZERO_CLAUSES,
            expected="at least one SECTION with text",
        )
    return ParsedDocument(profile=PROFILE, clauses=clauses)
