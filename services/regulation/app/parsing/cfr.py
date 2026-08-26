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
from .ladder import CFR as _LADDER
from .model import ParsedClause, ParsedDocument, ParseError
from .tables import Table, html_tables, table_clauses

PROFILE = "cfr_structured"

#: This profile takes a parsed XML root, not the archived bytes. See :mod:`.` .
ACCEPTS_RAW = False

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
    section_index = len(clauses) - 1
    paragraphs, pending = _paragraphs_and_tables(node)
    produced = _LADDER.segment_paragraphs(paragraphs, prefix=section_prefix, clauses=clauses)
    _attach_tables(
        pending,
        produced,
        clauses=clauses,
        section_prefix=section_prefix,
        section_index=section_index,
    )


def _paragraphs_and_tables(node: Element) -> tuple[list[str], list[tuple[int, Table, str | None]]]:
    """Section children in document order: the paragraph texts, and where each table sits.

    A table's position **is** its attachment. 21 CFR 820.10 carries its table between ``(c)(2)`` and
    ``(d)``, and its own caption agrees — *"Table 1 to Paragraph (c)(2)"* — so the preceding
    paragraph identifies the owner without parsing that prose, which two of the three tables in
    scope do not have anyway.

    The table is **not** flattened into the paragraph run, and that is load-bearing rather than
    tidy: the first column of 21 CFR 822.19's table is literally ``(a) Should result in…``,
    ``(b) …``. Fed to the ladder those read as paragraph designators and would open two phantom
    levels under the section, taking the rest of the section's paragraphs with them.
    """
    paragraphs: list[str] = []
    tables: list[tuple[int, Table, str | None]] = []
    for child in node:
        if child.tag == "P":
            if text := _element_text(child):
                paragraphs.append(text)
            continue
        for table in html_tables(child):
            tables.append((len(paragraphs), table, _caption(child)))
    return paragraphs, tables


def _caption(node: Element) -> str | None:
    """``<CAPTION>`` text — *"Table 1 to Paragraph (c)(2)"* — where the table names itself."""
    caption = next(node.iter("CAPTION"), None)
    return normalize_text("".join(caption.itertext())) or None if caption is not None else None


def _attach_tables(
    pending: list[tuple[int, Table, str | None]],
    produced: list[int],
    *,
    clauses: list[ParsedClause],
    section_prefix: tuple[str, ...],
    section_index: int,
) -> None:
    """Emit each table under the paragraph it followed, numbered within its section.

    A table before the section's first paragraph hangs off the section itself — there is no
    preceding paragraph to own it, and inventing one would put a table under a provision that does
    not exist.
    """
    for number, (after, table, caption) in enumerate(pending, start=1):
        if after > 0 and produced:
            parent_index = produced[min(after, len(produced)) - 1]
            parent = clauses[parent_index].path_segments
        else:
            parent_index, parent = section_index, section_prefix
        clauses.extend(
            table_clauses(
                tuple(parent),
                table,
                table_segment=f"Table {number}",
                row_segment=lambda ordinal: f"Row {ordinal}",
                base=len(clauses),
                heading=caption,
                parent_index=parent_index,
            )
        )


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
