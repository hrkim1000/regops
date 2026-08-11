"""Every read `monitoring` makes across the service boundary, in one place.

`regulation` owns the clause store and everything derived from it; `monitoring` begins where writing
ends (ADR-0009 decision 2). CLAUDE.md § Table ownership makes the rule explicit — *reads across a
boundary are raw SQL; never import another service's ORM model* — and keeping all of them in one
module means the seam is a file a reviewer can check rather than a habit scattered through six.

**Nothing in this module writes.** The only tables `monitoring` writes are its own three, through
the ORM. That is the phase1.4 acceptance criterion "static analysis or review confirms zero
`regulation` writes from `monitoring`", and this file is where that review starts and ends.

Every lookup is batched with ``= ANY(:ids)``. An amendment to 화장품법 produces one change event per
diff per claiming cell — 1,209 of them for a single real amendment before the ordinal fix — and a
per-row query would turn one alert into four figures of round trips.

The statements are declared once and wrapped twice, sync for the Celery worker and async for the
API. Two engines is a fact of the stack (``regops_shared.db``); two copies of a cross-seam query
would not be, and the second copy is the one that drifts.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from regops_shared.db import AsyncSession


@dataclass(frozen=True, slots=True)
class AmendmentRef:
    """The version an alert is about, and the dates the latency gate is measured against."""

    version_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    doc_type: str
    version_label: str | None
    effective_date: date | None
    #: The authority's own publication date. **Null where the source publishes none** — latency is
    #: then reported unmeasurable rather than zero (ADR-0003 decision 5).
    published_at: datetime | None
    retrieved_at: datetime


@dataclass(frozen=True, slots=True)
class ChangeEventRow:
    """One ``change_event`` joined to the diff it describes.

    The join is what makes suppression possible at all: the event carries no change kind, so
    "renumbering only" is a question about ``clause_diffs`` that only this read can answer.
    """

    event_id: uuid.UUID
    cell_id: uuid.UUID
    document_id: uuid.UUID
    detected_at: datetime
    clause_diff_id: uuid.UUID
    clause_path: str
    from_clause_path: str | None
    change_kind: str
    from_version_id: uuid.UUID | None


@dataclass(frozen=True, slots=True)
class CellRef:
    cell_id: uuid.UUID
    slug: str
    authority: str
    domain: str


# --- statements ---------------------------------------------------------------------------------

_AMENDMENT = text(
    """
    SELECT dv.id, dv.document_id, d.title, d.doc_type::text, dv.version_label,
           dv.effective_date, dv.published_at, dv.retrieved_at
    FROM document_versions dv
    JOIN documents d ON d.id = dv.document_id
    WHERE dv.id = :version_id
    """
)

_CHANGE_EVENTS = text(
    """
    SELECT ce.id, ce.cell_id, ce.document_id, ce.detected_at,
           cd.id, cd.clause_path, cd.from_clause_path, cd.change_kind::text, cd.from_version_id
    FROM change_events ce
    JOIN clause_diffs cd ON cd.id = ce.clause_diff_id
    WHERE cd.to_version_id = :version_id
    ORDER BY ce.cell_id, cd.clause_path
    """
)

#: Human-locked obligations whose evidence this amendment moved — the strongest grading input Phase
#: 1 has, and the one that needs the most care to read.
#:
#: By the time routing runs, the diff stage has already superseded those citations **and moved their
#: IRs from ``locked`` to ``stale``** in the same transaction (ADR-0004 decision 5). Filtering on
#: ``status = 'locked'`` would therefore find nothing and grade every amendment as if no obligation
#: rested on it. Draft IRs are staled by the same sweep and look identical afterwards; the two are
#: told apart by ``locked_at``, which only a human's lock ever sets. That is the fact worth grading
#: on — *someone asserted this obligation, and the text under it has changed.*
#:
#: Keyed by domain because ``irs`` carries ``domain_profile`` rather than a cell, and a cosmetic
#: subscriber should not be alerted at high severity because a SaMD obligation was staled by the
#: same shared instrument.
_LOCKED_IR_IMPACT = text(
    """
    SELECT ir.domain_profile::text, count(DISTINCT ir.id)
    FROM ir_citations ic
    JOIN irs ir ON ir.id = ic.ir_id
    JOIN clause_diffs cd ON cd.id = ic.superseded_by_diff_id
    WHERE cd.to_version_id = :version_id
      AND ir.locked_at IS NOT NULL
    GROUP BY 1
    """
)

_CELLS_BY_ID = text(
    "SELECT id, slug, authority::text, domain::text FROM cells WHERE id = ANY(:cell_ids)"
)

_CELL_BY_SLUG = text("SELECT id, slug, authority::text, domain::text FROM cells WHERE slug = :slug")

_DOCUMENT_TITLES = text("SELECT id, title FROM documents WHERE id = ANY(:ids)")

#: Coverage is *events that reached an alert* over *events emitted*, and the denominator lives on
#: the other side of the seam. Reporting only the numerator would let a routing bug read as perfect
#: coverage.
#: ``:since`` is **cast explicitly**, and that is not cosmetic. asyncpg prepares every statement
#: server-side, so a bare parameter appearing only as ``:since IS NULL`` gives PostgreSQL nothing to
#: infer a type from and the whole query fails with ``could not determine data type of parameter
#: $1`` — at request time, on the metrics endpoint, and nowhere else. The sync driver infers it
#: happily, which is exactly why this survived the worker-side suite.
_CHANGE_EVENT_TOTALS = text(
    """
    SELECT ce.cell_id, count(*)
    FROM change_events ce
    WHERE (CAST(:since AS timestamptz) IS NULL OR ce.detected_at >= CAST(:since AS timestamptz))
    GROUP BY 1
    """
)


# --- shaping ------------------------------------------------------------------------------------


def _amendment_ref(row) -> AmendmentRef:
    return AmendmentRef(
        version_id=row[0],
        document_id=row[1],
        document_title=row[2],
        doc_type=row[3],
        version_label=row[4],
        effective_date=row[5],
        published_at=row[6],
        retrieved_at=row[7],
    )


def _event_rows(rows) -> list[ChangeEventRow]:
    return [
        ChangeEventRow(
            event_id=row[0],
            cell_id=row[1],
            document_id=row[2],
            detected_at=row[3],
            clause_diff_id=row[4],
            clause_path=row[5],
            from_clause_path=row[6],
            change_kind=row[7],
            from_version_id=row[8],
        )
        for row in rows
    ]


def _cell_refs(rows) -> dict[uuid.UUID, CellRef]:
    return {
        row[0]: CellRef(cell_id=row[0], slug=row[1], authority=row[2], domain=row[3])
        for row in rows
    }


# --- sync (Celery workers) ----------------------------------------------------------------------


def amendment(session: Session, version_id: uuid.UUID) -> AmendmentRef | None:
    """The version and its document. ``None`` when the version does not exist."""
    row = session.execute(_AMENDMENT, {"version_id": version_id}).first()
    return _amendment_ref(row) if row is not None else None


def change_events_for_version(session: Session, version_id: uuid.UUID) -> list[ChangeEventRow]:
    """Every change event this amendment emitted, across every claiming cell.

    Ordered by cell then clause path so composing an alert produces a stable clause list — an alert
    whose contents reshuffle between two reads of the same amendment is one nobody can compare with
    yesterday's.
    """
    return _event_rows(session.execute(_CHANGE_EVENTS, {"version_id": version_id}).all())


def locked_ir_impact(session: Session, version_id: uuid.UUID) -> dict[str, int]:
    """``{domain: count}`` of human-locked obligations this amendment staled."""
    return {
        row[0]: row[1]
        for row in session.execute(_LOCKED_IR_IMPACT, {"version_id": version_id}).all()
    }


def cells_by_id(session: Session, cell_ids: list[uuid.UUID]) -> dict[uuid.UUID, CellRef]:
    """Resolve cells in one query. The unit of subscription, so this is on every routing path."""
    if not cell_ids:
        return {}
    return _cell_refs(session.execute(_CELLS_BY_ID, {"cell_ids": cell_ids}).all())


# --- async (FastAPI) ------------------------------------------------------------------------------


async def cells_by_id_async(
    db: AsyncSession, cell_ids: list[uuid.UUID]
) -> dict[uuid.UUID, CellRef]:
    if not cell_ids:
        return {}
    return _cell_refs((await db.execute(_CELLS_BY_ID, {"cell_ids": cell_ids})).all())


async def cell_by_slug_async(db: AsyncSession, slug: str) -> CellRef | None:
    """One cell by its ``{authority}_{domain}`` slug — what a subscription request names."""
    row = (await db.execute(_CELL_BY_SLUG, {"slug": slug})).first()
    if row is None:
        return None
    return CellRef(cell_id=row[0], slug=row[1], authority=row[2], domain=row[3])


async def document_titles_async(
    db: AsyncSession, document_ids: list[uuid.UUID]
) -> dict[uuid.UUID, str]:
    """Titles for a page of alerts, in one query rather than one per row."""
    if not document_ids:
        return {}
    return {row[0]: row[1] for row in (await db.execute(_DOCUMENT_TITLES, {"ids": document_ids}))}


async def change_event_totals_async(
    db: AsyncSession, *, since: datetime | None = None
) -> dict[uuid.UUID, int]:
    """``{cell_id: change events emitted}`` — the denominator of detection coverage."""
    return {row[0]: row[1] for row in (await db.execute(_CHANGE_EVENT_TOTALS, {"since": since}))}


__all__ = [
    "AmendmentRef",
    "CellRef",
    "ChangeEventRow",
    "amendment",
    "cell_by_slug_async",
    "cells_by_id",
    "cells_by_id_async",
    "change_event_totals_async",
    "change_events_for_version",
    "document_titles_async",
    "locked_ir_impact",
]
