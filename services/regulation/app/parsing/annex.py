"""Annex profile — table mode, prose mode, and forms.

An annex is its own `Document` (ADR-0012) and its rows are `Clause` rows (ADR-0014). This profile
picks how to read one, and the branch is on the authority's own **별표구분**, never on domain:

===========  =======================================================================
``별표``     a table where box-drawing is present, prose where it is not
``서식``     one clause for the whole form
``별지``     one clause for the whole form
===========  =======================================================================

**The 서식/별지 branch is load-bearing, not an optimisation.** 197 of the 278 annex documents in the
gated corpus are blank application templates. Their box-drawing is *layout* — field boxes to be
filled in — and running the table parser over them would manufacture hundreds of clauses out of
empty form furniture, none of which carries an obligation. Measured: 서식 and 별지 hold 62 table
rows between them against 별표's 1,937 (ADR-0014).

Paths follow ADR-0014 decision 3: the annex identity is repeated as the first segment, so a citation
reads correctly when rendered apart from its document.

    별표2/표1/행3      a limit-table row
    별표3/1/가         a prose item inside an annex
    서식1              a whole form
"""

from __future__ import annotations

from xml.etree.ElementTree import Element

from regops_shared.constants import ClauseKind, DriftSignal

from ..canonicalize import normalize_text
from ..connectors.law_go_kr import annex_identity
from .dates import annex_effective_dates, enforcement_phrase, envelope_effective_date
from .markers import match_marker
from .model import ParsedClause, ParsedDocument, ParseError
from .outline import Ladder, segment_outline
from .tables import Table, find_tables, is_rule, table_clauses

PROFILE = "annex"

#: This profile takes a parsed XML root, not the archived bytes. See :mod:`.` .
ACCEPTS_RAW = False

#: 별표구분 values whose content is a blank template rather than data.
FORM_KINDS = frozenset({"서식", "별지"})


def parse(root: Element, *, annex_segment: str) -> ParsedDocument:
    """Parse one annex.

    ``annex_segment`` is the ``별표2`` / ``서식1`` label — the tail of the annex Document's
    ``canonical_key``. Taking it from the key rather than re-deriving it from the XML guarantees the
    path and the document identity cannot disagree, which is the failure ADR-0012's amendment was
    written after.
    """
    unit = _unit_for(root, annex_segment)
    if unit is None:
        raise ParseError(
            f"{annex_segment}: no 별표단위 in the archived response matches this annex",
            signal=DriftSignal.MISSING_ROOT,
            expected=f"별표단위 resolving to {annex_segment}",
        )

    content = normalize_text(unit.findtext("별표내용") or "")
    if not content:
        # ADR-0003 decision 10's fallback case, and phase 1.1 requires it to be *raised* rather than
        # logged and skipped: an annex silently absent is the worst outcome for the cell whose
        # obligations live in them. `attachments` holds the authority's own HWP/PDF links for a
        # human to follow — implementing that fetch is phase 2.0, alerting on it is now.
        raise ParseError(
            f"{annex_segment}: 별표내용 is empty. The annex text did not arrive inline; the "
            "authority's own file links are recorded in `attachments` as the fallback",
            signal=DriftSignal.EMPTY_ANNEX_BODY,
            expected="non-empty 별표내용",
        )

    # An annex's date is its **own** where the authority states one (ADR-0012, amended 2026-08-06):
    # 별표시행일자문자열 names the annexes taking effect on each date. Falling back to the parent's
    # 시행일자 is right for an annex the amendment did not touch — it takes effect with its body.
    stated = annex_effective_dates(root).get(annex_segment)
    document = ParsedDocument(
        profile=PROFILE,
        effective_date=stated or envelope_effective_date(root),
        effective_date_phrase=enforcement_phrase(root),
    )

    kind = normalize_text(unit.findtext("별표구분") or "별표")
    if kind in FORM_KINDS:
        document.clauses = [_form_clause(annex_segment, unit, content)]
        return document

    document.clauses = _annex_body(annex_segment, content)
    if not document.clauses:
        raise ParseError(
            f"{annex_segment}: 별표내용 yielded no clause — neither a table nor an outline marker",
            signal=DriftSignal.ZERO_CLAUSES,
            expected="a box-drawing table or numbered prose",
        )
    return document


def _unit_for(root: Element, annex_segment: str) -> Element | None:
    """Find the ``별표단위`` whose ``(별표구분, 별표번호, 별표가지번호)`` renders to this segment.

    The triple is what the authority's own ``별표키`` encodes and is unique by construction; keying
    on 별표번호 alone silently merged 105 units corpus-wide (ADR-0012 amendment).
    """
    for unit in root.iter("별표단위"):
        kind, label = annex_identity(unit)
        if f"{kind}{label}" == annex_segment:
            return unit
    return None


def _form_clause(segment: str, unit: Element, content: str) -> ParsedClause:
    """A whole 서식/별지 as one clause. Its box-drawing is layout, not data."""
    return ParsedClause(
        path_segments=(segment,),
        text=content,
        kind=ClauseKind.FORM,
        heading=normalize_text(unit.findtext("별표제목") or "") or None,
    )


def _annex_body(segment: str, content: str) -> list[ParsedClause]:
    """Interleave the annex's tables and the prose around them, in document order.

    Prose blocks are numbered ``문단1``, ``문단2``, … **only when the annex also has tables.** A
    table-bearing annex has several prose blocks — 별표 2 carries a ``* 보존제 성분`` caption before
    each of its four tables — and without a per-block segment two of them would land on the same
    ``clause_path``. A prose-only annex has one block, so the extra level would be noise in every
    citation it produces.
    """
    lines = content.split("\n")
    tables = find_tables(content)
    if not tables:
        return _prose(segment, lines, prefix=(segment,))

    clauses: list[ParsedClause] = []
    spans = [(table.start_line, _table_end(lines, table.start_line), table) for table in tables]
    cursor = 0
    block = 0
    for number, (start, end, table) in enumerate(spans, start=1):
        block += 1
        clauses.extend(_prose(segment, lines[cursor:start], prefix=(segment, f"문단{block}")))
        clauses.extend(_table(segment, number, table, base=len(clauses)))
        cursor = end
    clauses.extend(_prose(segment, lines[cursor:], prefix=(segment, f"문단{block + 1}")))
    return clauses


def _table_end(lines: list[str], start: int) -> int:
    """Index just past the table's closing rule, or the end of the annex if it never closes."""
    for index in range(start + 1, len(lines)):
        stripped = lines[index].strip()
        if is_rule(lines[index]) and stripped.startswith(("└", "┗")):
            return index + 1
    return len(lines)


def _table(segment: str, number: int, table: Table, *, base: int) -> list[ParsedClause]:
    """One ``표`` clause carrying the column map, then one ``행`` clause per logical row.

    The structure lives in :func:`table_clauses`, shared with ``cfr_structured``; what stays here is
    the naming convention, which belongs to the instrument (ADR-0014 decision 3).
    """
    return table_clauses(
        (segment,),
        table,
        table_segment=f"표{number}",
        row_segment=lambda ordinal: f"행{ordinal}",
        base=base,
    )


def _prose(segment: str, lines: list[str], *, prefix: tuple[str, ...]) -> list[ParsedClause]:
    """Prose around the tables, segmented on the shared outline ladder.

    57 of the 81 별표 in the gated corpus contain no table at all — 별표 3 인체 세포ㆍ조직 배양액
    안전기준 is numbered prose carrying real obligations — so this is the majority path, not a
    leftover branch.

    Text *before* the first marker is kept as a ``서문`` clause. It is where an annex states its own
    title and the caption identifying the table that follows (``* 보존제 성분``), and dropping it
    would lose the only thing distinguishing four otherwise identical ingredient tables.
    """
    text = "\n".join(lines).strip()
    if not text:
        return []

    body = normalize_text(text).split("\n")
    first = next((i for i, line in enumerate(body) if match_marker(line)), None)

    if first is None:
        return [ParsedClause(path_segments=prefix, text="\n".join(body), kind=ClauseKind.PROSE)]

    clauses: list[ParsedClause] = []
    if preamble := "\n".join(body[:first]).strip():
        clauses.append(
            ParsedClause(
                path_segments=(*prefix, "서문") if len(prefix) == 1 else prefix,
                text=preamble,
                kind=ClauseKind.PROSE,
            )
        )
    clauses.extend(
        segment_outline("\n".join(body[first:]), prefix=prefix, ladder=Ladder.DISCOVERED)
    )
    return clauses


__all__ = ["FORM_KINDS", "PROFILE", "parse"]
