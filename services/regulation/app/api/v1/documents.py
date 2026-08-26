"""Reading what was ingested — cells, documents, versions, and the archived bytes themselves.

Read-only by design. Everything that *writes* the clause store is the pipeline
(CLAUDE.md § The seam); this router only exposes what the pipeline produced, so a human can see
that a source was checked at time T and what came back.

Two shapes worth noting:

- **Annexes are child documents** (ADR-0012), so a listing that does not say so reads as inflated:
  a 고시 with four 별표 is five rows. ``parent_only`` and ``annex_count`` make the tree visible.
- **The raw endpoint does not wear the envelope.** It streams the archived artefact with its own
  content type. Wrapping 1.8 MB of XML in JSON to satisfy a convention meant for JSON resources
  would help nobody; the metadata that *is* enveloped lives on the version detail beside it.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import aliased

from regops_shared.api import Meta, ok
from regops_shared.auth import Principal, get_current_principal
from regops_shared.constants import (
    ADMIN_RULE_DOC_TYPES,
    DOC_CATEGORY_ORDER,
    STATUTE_DOC_TYPES,
    DocCategory,
    VersionStatus,
    doc_category,
    in_force_date,
    version_status,
)
from regops_shared.db import AsyncSession, get_db
from regops_shared.storage import read_archived

from ...models import (
    Attachment,
    Cell,
    Document,
    DocumentCell,
    DocumentVersion,
)

router = APIRouter(prefix="/api/v1", tags=["regulation"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[Principal, Depends(get_current_principal)]

#: Alias for the parent row, so a listing can read the parent's ``doc_type`` in the same query. An
#: annex cannot be categorised without it — 별표 of a 법령 and 별표 of a 고시 both carry
#: ``doc_type = 'annex'``.
_Parent = aliased(Document, name="parent_doc")

#: SQL mirror of :func:`doc_category`, so ordering happens in the database rather than over a page
#: that has already been sliced. The Python function stays the single definition of the *rule*; this
#: expression exists only because ``ORDER BY`` cannot call it.
#:
#: The membership sets are **imported, not restated**. They used to be inline literals here, which
#: is a copy that only stays true while nobody adds a ``doc_type`` — and adding two (``regulation``,
#: ``codified_statute``) is exactly what made every FDA document sort as ``other`` while the Python
#: side was being corrected. ``sorted()`` only fixes the emitted parameter order so the SQL is
#: stable to read in a log.
_CATEGORY_SQL = case(
    (Document.doc_type.in_(sorted(STATUTE_DOC_TYPES)), DocCategory.STATUTE.value),
    (Document.doc_type.in_(sorted(ADMIN_RULE_DOC_TYPES)), DocCategory.ADMIN_RULE.value),
    (
        and_(Document.doc_type == "annex", _Parent.doc_type.in_(sorted(ADMIN_RULE_DOC_TYPES))),
        DocCategory.ADMIN_RULE_ANNEX.value,
    ),
    (Document.doc_type == "annex", DocCategory.STATUTE_ANNEX.value),
    (Document.doc_type == "feed", DocCategory.FEED.value),
    else_=DocCategory.OTHER.value,
)

_CATEGORY_RANK = case(
    {category.value: rank for rank, category in enumerate(DOC_CATEGORY_ORDER)},
    value=_CATEGORY_SQL,
    else_=len(DOC_CATEGORY_ORDER),
)


@router.get("/cells")
async def list_cells(db: DbSession, _: CurrentUser) -> dict[str, Any]:
    """The 8 cells, with what has actually been ingested into each.

    Counts are the point: a cell with zero documents is not "empty pending work", it is a cell no
    connector reaches yet, and the UI should be able to say so without a second call.
    """
    cells = list(await db.scalars(select(Cell).order_by(Cell.slug)))

    # Counted per category rather than body-vs-annex, because that is how the authority groups its
    # own holdings and therefore how an RA reads them: "9 법령, 59 고시" not "68 본문".
    rows = (
        await db.execute(
            select(
                DocumentCell.cell_id,
                _CATEGORY_SQL.label("category"),
                func.count().label("n"),
            )
            .join(Document, Document.id == DocumentCell.document_id)
            .outerjoin(_Parent, _Parent.id == Document.parent_document_id)
            .group_by(DocumentCell.cell_id, _CATEGORY_SQL)
        )
    ).all()
    counts: dict[uuid.UUID, dict[str, int]] = {}
    for row in rows:
        counts.setdefault(row.cell_id, {})[row.category] = row.n

    return ok(
        [
            {
                "id": str(cell.id),
                "slug": cell.slug,
                "authority": cell.authority.value,
                "domain": cell.domain.value,
                # Retained: existing callers read these, and "how many instruments" is still a
                # question worth one number.
                "document_count": sum(
                    n
                    for category, n in counts.get(cell.id, {}).items()
                    if category in {DocCategory.STATUTE, DocCategory.ADMIN_RULE}
                ),
                "annex_count": sum(
                    n
                    for category, n in counts.get(cell.id, {}).items()
                    if category in {DocCategory.STATUTE_ANNEX, DocCategory.ADMIN_RULE_ANNEX}
                ),
                "categories": {
                    category.value: counts.get(cell.id, {}).get(category.value, 0)
                    for category in DOC_CATEGORY_ORDER
                },
            }
            for cell in cells
        ]
    )


@router.get("/documents")
async def list_documents(
    db: DbSession,
    _: CurrentUser,
    cell_id: uuid.UUID | None = Query(None, description="Restrict to one cell"),
    parent_only: bool = Query(True, description="Exclude annex child documents"),
    q: str | None = Query(None, min_length=1, max_length=200, description="Title contains"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    stmt = select(Document, _CATEGORY_SQL.label("category")).outerjoin(
        _Parent, _Parent.id == Document.parent_document_id
    )
    if cell_id is not None:
        stmt = stmt.join(DocumentCell, DocumentCell.document_id == Document.id).where(
            DocumentCell.cell_id == cell_id
        )
    if parent_only:
        stmt = stmt.where(Document.parent_document_id.is_(None))
    if q:
        stmt = stmt.where(Document.title.ilike(f"%{q}%"))

    total = await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    # Category first, then title. Ordering in SQL rather than over an already-sliced page is what
    # keeps the grouping correct across pagination — a client-side sort would only ever group the
    # 50 rows it happens to hold. Postgres orders Hangul by code point, which *is* 가나다순 for the
    # Hangul Syllables block, so no collation is configured for it.
    result = (
        await db.execute(
            stmt.order_by(_CATEGORY_RANK, Document.title)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    rows = [row[0] for row in result]
    categories = {row[0].id: row.category for row in result}

    ids = [row.id for row in rows]
    annex_counts = {
        row.parent_document_id: row.n
        for row in (
            await db.execute(
                select(Document.parent_document_id, func.count().label("n"))
                .where(Document.parent_document_id.in_(ids))
                .group_by(Document.parent_document_id)
            )
        ).all()
    }
    version_counts = {
        row.document_id: row.n
        for row in (
            await db.execute(
                select(DocumentVersion.document_id, func.count().label("n"))
                .where(DocumentVersion.document_id.in_(ids))
                .group_by(DocumentVersion.document_id)
            )
        ).all()
    }
    # 시행예정 — 공포되었으나 아직 시행 전. Surfaced on the list because otherwise a 법령 with four
    # pending amendments is indistinguishable from one with none: both read as a single row whose
    # only hint is a version count (ADR-0016).
    pending_counts = {
        row.document_id: row.n
        for row in (
            await db.execute(
                select(DocumentVersion.document_id, func.count().label("n"))
                .where(
                    DocumentVersion.document_id.in_(ids),
                    DocumentVersion.effective_date > func.current_date(),
                )
                .group_by(DocumentVersion.document_id)
            )
        ).all()
    }

    return ok(
        [
            _document_out(
                row,
                annex_counts.get(row.id, 0),
                version_counts.get(row.id, 0),
                category=categories.get(row.id),
                pending_version_count=pending_counts.get(row.id, 0),
            )
            for row in rows
        ],
        meta=Meta(page=page, page_size=page_size, total=total),
    )


@router.get("/documents/{document_id}")
async def get_document(document_id: uuid.UUID, db: DbSession, _: CurrentUser) -> dict[str, Any]:
    document = await db.get(Document, document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")

    annexes = list(
        await db.scalars(
            select(Document)
            .where(Document.parent_document_id == document_id)
            .order_by(Document.annex_no)
        )
    )
    parent = (
        await db.get(Document, document.parent_document_id) if document.parent_document_id else None
    )
    cells = list(
        await db.scalars(
            select(Cell)
            .join(DocumentCell, DocumentCell.cell_id == Cell.id)
            .where(DocumentCell.document_id == document_id)
            .order_by(Cell.slug)
        )
    )
    versions = list(
        await db.scalars(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.retrieved_at.desc())
        )
    )
    statuses = _statuses(versions)

    return ok(
        {
            **_document_out(
                document,
                len(annexes),
                len(versions),
                parent_doc_type=parent.doc_type.value if parent else None,
            ),
            "cells": [c.slug for c in cells],
            "parent": (
                {"id": str(parent.id), "title": parent.title, "canonical_key": parent.canonical_key}
                if parent
                else None
            ),
            "annexes": [
                {
                    "id": str(a.id),
                    "annex_no": a.annex_no,
                    "title": a.title,
                    "canonical_key": a.canonical_key,
                }
                for a in annexes
            ],
            "versions": [_version_out(v, status=statuses[v.id].value) for v in versions],
        }
    )


@router.get("/document-versions/{version_id}")
async def get_version(version_id: uuid.UUID, db: DbSession, _: CurrentUser) -> dict[str, Any]:
    version = await db.get(DocumentVersion, version_id)
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Version not found")
    document = await db.get(Document, version.document_id)
    attachments = list(
        await db.scalars(
            select(Attachment)
            .where(Attachment.document_version_id == version_id)
            .order_by(Attachment.ordinal)
        )
    )
    # Siblings, because "is this the one in force?" cannot be answered from this row alone.
    siblings = list(
        await db.scalars(
            select(DocumentVersion).where(DocumentVersion.document_id == version.document_id)
        )
    )
    return ok(
        {
            **_version_out(version, status=_statuses(siblings)[version.id].value),
            "document": (
                {
                    "id": str(document.id),
                    "title": document.title,
                    "canonical_key": document.canonical_key,
                    "doc_type": document.doc_type.value,
                    "annex_no": document.annex_no,
                }
                if document
                else None
            ),
            "attachments": [
                {
                    "kind": a.kind.value,
                    "title": a.title,
                    "file_format": a.file_format,
                    "source_url": a.source_url,
                }
                for a in attachments
            ],
        }
    )


@router.get("/document-versions/{version_id}/raw")
async def get_version_raw(
    version_id: uuid.UUID, db: DbSession, _: CurrentUser, download: bool = False
) -> Response:
    """Stream the archived artefact exactly as the authority returned it.

    Deliberately not enveloped — this is a byte stream, not a JSON resource. It is also the *only*
    place the raw archive is exposed, and it reads from MinIO rather than the network: everything
    downstream reads from the archive (ADR-0002 decision 6).

    Anything reachable here is credential-free by construction: ``archive_bytes`` refuses to store
    a payload containing a configured source credential, so the guard is upstream of this endpoint
    rather than duplicated in it.
    """
    version = await db.get(DocumentVersion, version_id)
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Version not found")

    # MinIO's client is synchronous; reading a 1.8 MB object on the event loop would stall every
    # other request on this worker.
    try:
        payload = await asyncio.to_thread(read_archived, version.raw_object_key)
    except Exception as exc:  # surfaced as 502; the cause travels on the exception chain
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            f"Archived object {version.raw_object_key} could not be read",
        ) from exc

    headers = {"X-Content-Hash": version.content_hash, "X-Raw-Object-Key": version.raw_object_key}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="{version_id}.xml"'
    return Response(
        content=payload,
        media_type=version.content_type or "application/octet-stream",
        headers=headers,
    )


# --- serializers ---------------------------------------------------------------


def _document_out(
    document: Document,
    annex_count: int,
    version_count: int,
    *,
    category: str | None = None,
    parent_doc_type: str | None = None,
    pending_version_count: int = 0,
) -> dict[str, Any]:
    return {
        "id": str(document.id),
        "canonical_key": document.canonical_key,
        "title": document.title,
        "doc_type": document.doc_type.value,
        # The authority's own bucket. Derived, never stored — see `doc_category`. Passed in where
        # the caller already computed it in SQL, so the two cannot disagree.
        "category": category or doc_category(document.doc_type.value, parent_doc_type).value,
        "annex_no": document.annex_no,
        "parent_document_id": (
            str(document.parent_document_id) if document.parent_document_id else None
        ),
        "annex_count": annex_count,
        "version_count": version_count,
        #: 공포되었으나 아직 시행 전인 버전 수. Derived from the dates, never stored (ADR-0016).
        "pending_version_count": pending_version_count,
    }


def _statuses(versions: list[DocumentVersion]) -> dict[uuid.UUID, VersionStatus]:
    """Classify every version of one document against the same "today" and the same in-force date.

    Computed over the whole set on purpose. Which version is *in force* is a property of the set —
    the latest whose date has arrived — so classifying rows one at a time cannot produce it.
    """
    today = date.today()
    in_force = in_force_date((v.effective_date for v in versions), today=today)
    return {
        v.id: version_status(v.effective_date, in_force=in_force, today=today) for v in versions
    }


def _version_out(version: DocumentVersion, *, status: str | None = None) -> dict[str, Any]:
    """The three dates travel together on purpose — a reader must be able to see that
    ``published_at`` is null rather than silently reading ``retrieved_at`` as publication.

    ``status`` (시행중 / 시행예정 / 지난 버전) is computed by the caller, which is the only place
    that can: it depends on the *sibling* versions, not on this row. Classifying a version alone
    would call every future date "pending" and never identify which past one is actually in force.
    """
    return {
        "id": str(version.id),
        "status": status,
        "version_label": version.version_label,
        "language": version.language,
        "content_hash": version.content_hash,
        "raw_object_key": version.raw_object_key,
        "raw_bytes": version.raw_bytes,
        "content_type": version.content_type,
        "retrieved_at": version.retrieved_at.isoformat(),
        "published_at": version.published_at.isoformat() if version.published_at else None,
        "effective_date": version.effective_date.isoformat() if version.effective_date else None,
        "effective_date_phrase": version.effective_date_phrase,
        "parser_version": version.parser_version,
    }


__all__ = ["router"]
