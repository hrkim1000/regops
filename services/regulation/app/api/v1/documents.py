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
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select

from regops_shared.api import Meta, ok
from regops_shared.auth import Principal, get_current_principal
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


@router.get("/cells")
async def list_cells(db: DbSession, _: CurrentUser) -> dict[str, Any]:
    """The 8 cells, with what has actually been ingested into each.

    Counts are the point: a cell with zero documents is not "empty pending work", it is a cell no
    connector reaches yet, and the UI should be able to say so without a second call.
    """
    cells = list(await db.scalars(select(Cell).order_by(Cell.slug)))

    counts = {
        (row.cell_id, row.is_annex): row.n
        for row in (
            await db.execute(
                select(
                    DocumentCell.cell_id,
                    (Document.parent_document_id.is_not(None)).label("is_annex"),
                    func.count().label("n"),
                )
                .join(Document, Document.id == DocumentCell.document_id)
                .group_by(DocumentCell.cell_id, "is_annex")
            )
        ).all()
    }

    return ok(
        [
            {
                "id": str(cell.id),
                "slug": cell.slug,
                "authority": cell.authority.value,
                "domain": cell.domain.value,
                "document_count": counts.get((cell.id, False), 0),
                "annex_count": counts.get((cell.id, True), 0),
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
    stmt = select(Document)
    if cell_id is not None:
        stmt = stmt.join(DocumentCell, DocumentCell.document_id == Document.id).where(
            DocumentCell.cell_id == cell_id
        )
    if parent_only:
        stmt = stmt.where(Document.parent_document_id.is_(None))
    if q:
        stmt = stmt.where(Document.title.ilike(f"%{q}%"))

    total = await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = list(
        await db.scalars(
            stmt.order_by(Document.title).offset((page - 1) * page_size).limit(page_size)
        )
    )

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

    return ok(
        [
            _document_out(row, annex_counts.get(row.id, 0), version_counts.get(row.id, 0))
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

    return ok(
        {
            **_document_out(document, len(annexes), len(versions)),
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
            "versions": [_version_out(v) for v in versions],
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
    return ok(
        {
            **_version_out(version),
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


def _document_out(document: Document, annex_count: int, version_count: int) -> dict[str, Any]:
    return {
        "id": str(document.id),
        "canonical_key": document.canonical_key,
        "title": document.title,
        "doc_type": document.doc_type.value,
        "annex_no": document.annex_no,
        "parent_document_id": (
            str(document.parent_document_id) if document.parent_document_id else None
        ),
        "annex_count": annex_count,
        "version_count": version_count,
    }


def _version_out(version: DocumentVersion) -> dict[str, Any]:
    """The three dates travel together on purpose — a reader must be able to see that
    ``published_at`` is null rather than silently reading ``retrieved_at`` as publication."""
    return {
        "id": str(version.id),
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
