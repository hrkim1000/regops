"""Parser profiles — bytes in, clauses out. No database, no network.

**Profile selection is keyed on the shape of the source, never on the domain.** That is the
architecture bet ADR-0002 decision 3 makes and phase 1.1 exists to test: 화장품법 and 의료기기법 go
through the same profile because they are both 법령, and 화장품 안전기준 규정 and 의료기기 기준규격
go through the same profile because they are both 고시. A profile keyed on `samd` vs `cosmetic`
would be the falsifier firing.

There are three, and each exists because the *envelope* differs:

===================  ==================================================================
``law_structured``   법령 — 조문/항/호/목 arrive as XML elements; the hierarchy is given
``admrul_text``      고시 — flat ``조문내용`` blobs; the hierarchy must be segmented out
``annex``            별표/서식/별지 — a child Document, read in table, prose or form mode
===================  ==================================================================

Both gated cells use all three. `mfds_cosmetic` has 법령 (화장품법), 고시 (안전기준 규정) and
table-dense annexes; `mfds_samd` has 법령 (의료기기법), 고시 (기준규격) and the same box-drawing
annexes. Neither the split nor any profile is domain-conditional.
"""

from __future__ import annotations

from xml.etree.ElementTree import Element

import structlog
from defusedxml.ElementTree import ParseError as XMLParseError
from defusedxml.ElementTree import fromstring as parse_xml

from regops_shared.constants import DocType, DriftSignal

from . import admrul, annex, law
from .model import ParsedClause, ParsedDocument, ParseError

log = structlog.get_logger(__name__)

#: ``documents.doc_type`` → profile module. 법령 instruments (법률 · 대통령령 · 총리령/부령) all use
#: the structured profile; a 고시 uses the text profile. Annexes route on ``doc_type`` too, since
#: ADR-0012 makes them their own Document.
_BY_DOC_TYPE = {
    DocType.LAW: law,
    DocType.DECREE: law,
    DocType.ENFORCEMENT_RULE: law,
    DocType.NOTICE: admrul,
    DocType.ANNEX: annex,
}


def profile_for(doc_type: DocType) -> str:
    """Name of the profile that will handle this document type; ``""`` if there is none."""
    module = _BY_DOC_TYPE.get(doc_type)
    return module.PROFILE if module else ""


def is_parseable(doc_type: DocType) -> bool:
    """Does this document type yield clauses at all?

    ``FEED`` does not, and that is not a gap. An RSS board is a **change signal**: a list of
    announcements with a title and a ``pubDate``, carrying no regulation text — the 고시 it
    announces is fetched separately through 행정규칙 본문조회. There is nothing in a feed to
    segment, cite or diff at clause level.

    Callers must consult this before enqueueing a parse. Treating "no profile" as drift would delete
    the version (``_fail_closed``) and raise a spurious alert every time a board publishes an item —
    destroying the archived record of what the board said at time T, which is the only thing that
    makes the feed useful as a latency signal in the first place.
    """
    return doc_type in _BY_DOC_TYPE


def parse_document(
    raw: bytes,
    *,
    doc_type: DocType,
    canonical_key: str,
) -> ParsedDocument:
    """Parse archived bytes into a clause tree.

    ``canonical_key`` is used only for annexes, whose path segment is the tail after ``#`` — taking
    it from the key rather than re-deriving it from the XML is what guarantees a clause path and its
    document identity cannot disagree.

    Raises :class:`~.model.ParseError` on anything that is structure drift rather than regulatory
    change. The caller turns that into an operator alert, creates no version and emits no change
    event (ADR-0003 decision 6).
    """
    module = _BY_DOC_TYPE.get(doc_type)
    if module is None:
        raise ParseError(
            f"no parser profile for doc_type {doc_type.value!r}",
            signal=DriftSignal.MISSING_ROOT,
            expected="a document type with a registered profile",
        )

    root = _root(raw, canonical_key=canonical_key)

    if module is annex:
        _, _, segment = canonical_key.partition("#")
        if not segment:
            raise ParseError(
                f"{canonical_key}: an annex document has no '#' segment in its canonical_key",
                signal=DriftSignal.MISSING_ROOT,
                expected="canonical_key of the form <parent>#별표N",
            )
        parsed = annex.parse(root, annex_segment=segment)
    else:
        parsed = module.parse(root)

    _disambiguate(parsed, canonical_key=canonical_key)
    return parsed


def _disambiguate(parsed: ParsedDocument, *, canonical_key: str) -> None:
    """Guarantee ``clause_path`` is unique within the version, by suffixing repeats.

    A repeat means the source's own outline is ambiguous — an annex restarting ``1.`` under a
    section it never marked, most often. The two honest options are to drop the later clause or to
    give it a distinct address, and dropping it would lose an obligation silently while the count
    still looked plausible.

    The suffix is deterministic, so re-parsing the same bytes yields the same address and a citation
    stays resolvable. It is also *visible*: a ``~2`` in a citation is a legible signal that the
    authority's numbering repeated, which is the truth.
    """
    seen: dict[str, int] = {}
    for clause in parsed.clauses:
        path = clause.clause_path
        count = seen.get(path, 0) + 1
        seen[path] = count
        if count > 1:
            tail = f"{clause.path_segments[-1]}~{count}"
            clause.path_segments = (*clause.path_segments[:-1], tail)
            log.warning(
                "parse.duplicate_clause_path",
                document=canonical_key,
                clause_path=path,
                occurrence=count,
            )


def _root(raw: bytes, *, canonical_key: str) -> Element:
    """Parse the archived bytes as XML.

    A non-XML body is drift, not content. ``lawService.do?target=eflaw`` answers HTTP 500 with an
    XHTML error page (ADR-0016), and archiving or parsing that as a regulation would be worse than
    failing: it would create a version whose text is an error message.
    """
    try:
        return parse_xml(raw)
    except XMLParseError as exc:
        raise ParseError(
            f"{canonical_key}: archived body is not well-formed XML ({exc})",
            signal=DriftSignal.MISSING_ROOT,
            expected="an XML response envelope",
        ) from exc


__all__ = [
    "ParseError",
    "ParsedClause",
    "ParsedDocument",
    "is_parseable",
    "parse_document",
    "profile_for",
]
