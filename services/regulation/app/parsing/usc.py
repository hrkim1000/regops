"""``usc_text`` — the United States Code as govinfo publishes it, the fifth profile.

Selected by ``doc_type`` like the other four (:data:`DocType.CODIFIED_STATUTE`), never by authority
or cell — ADR-0002 decision 3. The FD&C Act needs its own profile for the same reason a CFR Part
did: its *envelope* differs from everything already handled. It is not :data:`DocType.LAW` because
that value names 법률, a rung of the Korean statutory ladder whose profile reads 조/항/호/목 as XML
**elements**; a USC granule is HTML and is not even well-formed XML (``undefined entity`` on the
first character reference), so routing it through ``law_structured`` would fail at the envelope
before reaching a single provision.

**What it shares with ``cfr_structured``, and why that is not authority-keying.** Both are US
drafting, so both nest paragraphs as ``(a)(1)(A)(i)`` designators inline at the head of the text.
Both read that ladder from :mod:`.ladder` rather than restating it. Sharing a *shape* helper
is not selecting on authority — selection stays on ``doc_type`` in :mod:`.`, and the falsifier
ADR-0002 decision 3 sets is about selection.

**What differs, and it is the whole of this module.** The eCFR gives containers as nested ``DIV``
elements, so ``cfr`` recovers the hierarchy by walking a tree. govinfo gives one **flat** run of
``<p>`` elements whose only structural signal is a ``class`` attribute — ``section-head``,
``subsection-head``, ``statutory-body-2em``. The hierarchy above paragraph level has to be
recovered from that sequence.

**Notes are not law, and there are more of them than there is law.** The chapter carries 4,149
``note-body`` blocks against 2,061 ``statutory-body`` — the Office of the Law Revision Counsel's
editorial apparatus (*Amendments*, *Effective Date of 1997 Amendment*, *Statutory Notes and Related
Subsidiaries*) outweighs the enacted text it annotates. Admitting it would put text that was never
enacted into citations and into the extraction denominator. It is excluded, and that exclusion is
worth more than half the corpus.

**Why exclusion is positional rather than by class name.** ``Q04`` appears 1,259 times and is a
presentational style used on *both* sides: it carries enacted text
(``(q)(1)(A) Except as provided in clause (B)...``) and it carries note banners
(``Statutory Notes and Related Subsidiaries``). No class-name rule can separate them. The layout
can: within a section, statutory text runs from ``section-head`` until the first ``source-credit``
or ``note-head``, and everything after that is apparatus until the next ``section-head``. That
reads the document's own arrangement instead of guessing from a style token.

**The source credit ends the section and is not kept.** ``(June 25, 1938, ch. 675, §201, 52 Stat.
1040; July 22, 1954 …)`` is the Public Law history of the section — the same kind of thing
``cfr_structured`` excludes as ``<SOURCE>`` and ``<CITA>``, and excluded here for the same reason:
it is provenance about the instrument, not a provision of it, and it states no obligation. It was
briefly written to ``clauses.source_ref`` and that was wrong twice over — semantically, because
that column holds the authority's own *identifier* (a 조문키) and is the primary renumber signal,
which a prose credit is not; and physically, because it is ``varchar(64)`` and 21 U.S.C. 321's
credit runs past two thousand characters. Where the credit is needed it is in the archived bytes,
which are what gets cited.

**Addressing.** ``path_segments`` is ``[subchapter, part, section, paragraph...]``, so
``21 U.S.C. 351(a)(1)`` is stored as ``Subchapter V/Part A/351/(a)/(1)``. Same shape as
``cfr_structured``, which stores ``Subpart B/820.35/(a)/(1)`` — containers are segments, the
section is its bare number, and the rendered citation is composed at citation time.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Final

from regops_shared.constants import ClauseKind, DriftSignal

from ..canonicalize import normalize_text
from .ladder import USC as _LADDER
from .model import ParsedClause, ParsedDocument, ParseError

PROFILE = "usc_text"

#: This profile reads HTML, so it takes the archived bytes rather than a parsed XML root.
ACCEPTS_RAW: Final[bool] = True

#: Container levels above a section, and how each renders in a path. ``CHAPTER`` is absent on
#: purpose: the chapter *is* the Document (ADR-0018 decision 12), exactly as a Part is for the CFR,
#: and a container is not a segment inside itself.
_CONTAINERS: Final[dict[str, str]] = {
    "subchapter-head": "Subchapter",
    "part-head": "Part",
    "subpart-head": "Subpart",
}

#: Blocks holding enacted text. The ``-Nem`` suffixes are indentation, which is presentational; the
#: designator sequence is what establishes depth, so the suffix is matched and then ignored.
_STATUTORY_PREFIXES: Final[tuple[str, ...]] = ("statutory-body",)
_STATUTORY_HEADS: Final[frozenset[str]] = frozenset(
    {"subsection-head", "paragraph-head", "subparagraph-head", "clause-head", "subclause-head"}
)

#: The ambiguous presentational style. Admitted only while the walker is inside statutory text —
#: see the module docstring.
_AMBIGUOUS: Final[str] = "Q04"

#: Blocks that end the enacted text of a section. ``source-credit`` is the Public Law provenance
#: that closes every section; a ``note-*`` head opens the apparatus where a section has no credit.
_TERMINATORS: Final[frozenset[str]] = frozenset(
    {"source-credit", "note-head", "note-sub-head", "futureamend-note-head"}
)

#: ``351. Adulterated drugs and devices`` → ``351`` and its heading, after the section sign is
#: stripped. A doubled sign and a range are kept verbatim (``360aaa to 360aaa-6. Omitted``) for the
#: reason CFR keeps ``820.20-820.30``: the authority published one node, and splitting it into
#: endpoints invents provisions that do not exist.
_SECTION = re.compile(r"^§{1,2}\s*(?P<number>[^.]{1,60}?)\.\s*(?P<heading>.*)$", re.DOTALL)

#: ``SUBCHAPTER V - DRUGS AND DEVICES`` → ``V``; also ``Part A - Drugs and Devices``.
_CONTAINER_NUMBER = re.compile(r"^[A-Za-z]+\s+(?P<number>[0-9A-Za-z]{1,12})\b")

_BLOCK_TAGS: Final[frozenset[str]] = frozenset({"p", "h1", "h2", "h3", "h4", "h5", "div"})


class _Blocks(HTMLParser):
    """Flatten the granule into an ordered ``(class, text)`` run.

    Stdlib rather than a parser dependency, for the reason :mod:`..connectors.mfds` gives: this is
    one publisher template, and the alternative is carrying lxml into every service image.

    Nested block tags are handled by attributing text to the **innermost open block that carries a
    class**, which keeps a ``<p class="statutory-body">`` inside a wrapper ``<div>`` from being
    filed under the wrapper.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[tuple[str, str]] = []
        self._stack: list[tuple[str, str, list[str]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in _BLOCK_TAGS:
            return
        css = ""
        for key, value in attrs:
            if key.lower() == "class" and value:
                css = value.strip()
        self._stack.append((tag, css, []))

    def handle_endtag(self, tag: str) -> None:
        for depth in range(len(self._stack) - 1, -1, -1):
            if self._stack[depth][0] == tag:
                for _, css, parts in self._stack[depth:]:
                    text = normalize_text("".join(parts))
                    if css and text:
                        self.blocks.append((css, text))
                del self._stack[depth:]
                return

    def handle_data(self, data: str) -> None:
        if self._stack:
            self._stack[-1][2].append(data)


def _container_segment(css: str, text: str) -> str | None:
    """``SUBCHAPTER V - DRUGS AND DEVICES`` → ``Subchapter V``; an unnumbered container vanishes.

    A container we cannot number is dropped from the address rather than guessed at, on the same
    reasoning ``cfr`` drops ``SUBJGRP``: an address that cannot be reproduced from the source is
    worse than a shorter one, because a citation resolved through it would not survive a reprint.
    """
    match = _CONTAINER_NUMBER.match(text)
    return f"{_CONTAINERS[css]} {match.group('number')}" if match else None


def _blocks_of(raw: bytes) -> list[tuple[str, str]]:
    parser = _Blocks()
    parser.feed(raw.decode("utf-8", errors="replace"))
    parser.close()
    return parser.blocks


def parse(raw: bytes) -> ParsedDocument:
    """A govinfo USCODE granule → clauses.

    The root is whatever granularity was fetched. A chapter granule carries the whole instrument in
    one artifact, which is what the connector asks for; a section granule is equally valid and
    yields one section, so fetch granularity stays a connector decision rather than a parsing one.

    ``effective_date`` is **not** read here. The USC is a codification republished annually
    (ADR-0018 decision 12): the version is the edition, and the dates that appear in the body belong
    to the editorial notes this profile excludes.
    """
    clauses: list[ParsedClause] = []
    containers: list[tuple[str, str]] = []  # (css, segment), outermost first
    order = list(_CONTAINERS)

    prefix: tuple[str, ...] = ()
    section_index: int | None = None
    paragraphs: list[str] = []
    in_apparatus = False

    def close_section() -> None:
        nonlocal paragraphs
        if section_index is not None and paragraphs:
            _LADDER.segment_paragraphs(paragraphs, prefix=prefix, clauses=clauses)
        paragraphs = []

    for css, text in _blocks_of(raw):
        if css in _CONTAINERS:
            close_section()
            section_index = None
            in_apparatus = False
            rank = order.index(css)
            containers = [item for item in containers if order.index(item[0]) < rank]
            segment = _container_segment(css, text)
            if segment:
                containers.append((css, segment))
            continue

        if css == "section-head":
            close_section()
            in_apparatus = False
            match = _SECTION.match(text)
            if match is None:
                # Not drift: a heading we cannot number is a heading we cannot address. Skipping it
                # costs one section; treating it as drift would discard the whole edition.
                section_index = None
                continue
            number = normalize_text(match.group("number"))
            heading = normalize_text(match.group("heading")) or None
            prefix = (*(segment for _, segment in containers), number)
            clauses.append(
                ParsedClause(
                    path_segments=prefix,
                    text=heading or number,
                    kind=ClauseKind.PROSE,
                    heading=heading,
                )
            )
            section_index = len(clauses) - 1
            continue

        if section_index is None:
            continue

        if css in _TERMINATORS:
            close_section()
            in_apparatus = True
            continue

        if in_apparatus or css.startswith("note-"):
            continue

        if css in _STATUTORY_HEADS or css.startswith(_STATUTORY_PREFIXES) or css == _AMBIGUOUS:
            paragraphs.append(text)

    close_section()

    if not clauses:
        raise ParseError(
            "no clauses were produced from the USC body",
            signal=DriftSignal.ZERO_CLAUSES,
            expected="at least one section-head block with statutory text",
        )
    return ParsedDocument(profile=PROFILE, clauses=clauses)


__all__ = ["ACCEPTS_RAW", "PROFILE", "parse"]
