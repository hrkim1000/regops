"""Building the retrieval index, and proving how much of the corpus it covers.

Embedding is RA-gated for the reason extraction is: it spends real model budget over every passage
of a version, and a ``viewer`` triggering it repeatedly is a cost incident rather than a permissions
question.

``/index/coverage`` exists because "the index is built" is otherwise an assumption. Retrieval that
silently covers 60% of a cell answers 60% of its questions well and the rest confidently badly —
and nothing about the second case looks different from the first at the API.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text

from regops_shared.api import ok
from regops_shared.audit import record
from regops_shared.auth import Principal, get_current_principal, require_roles
from regops_shared.constants import EMBEDDING_PASSAGE_VERSION, Role
from regops_shared.db import AsyncSession, get_db
from regops_shared.settings import get_settings

router = APIRouter(prefix="/api/v1", tags=["assistant"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[Principal, Depends(get_current_principal)]

SERVICE = "assistant"


@router.post("/document-versions/{version_id}/embed", status_code=status.HTTP_202_ACCEPTED)
async def embed_version(
    version_id: uuid.UUID,
    db: DbSession,
    principal: Annotated[Principal, Depends(require_roles([Role.RA, Role.ADMIN]))],
) -> dict[str, Any]:
    """Build this version's passage vectors now. Long work returns 202."""
    row = (
        await db.execute(
            text("SELECT parser_version FROM document_versions WHERE id = :id"),
            {"id": version_id},
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Version not found")
    if row[0] is None:
        # Embedding reads clauses, and an unparsed version has none. Enqueuing anyway would burn a
        # task to log "no clauses" and report success.
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Version has not been parsed; there are no clauses to embed",
        )

    from ...celery_app import celery_app

    task = celery_app.send_task(
        "assistant.embed_document_version", args=[str(version_id)], queue="assistant"
    )
    await record(
        db,
        service=SERVICE,
        action="embedding.triggered",
        actor_id=principal.id,
        entity_type="document_version",
        entity_id=version_id,
        payload={"task_id": task.id},
    )
    await db.commit()
    return {
        "code": status.HTTP_202_ACCEPTED,
        "status": "success",
        "message": "Embedding enqueued",
        "data": {"id": str(version_id), "task_id": task.id},
        "meta": None,
    }


@router.post("/index/embed", status_code=status.HTTP_202_ACCEPTED)
async def rebuild_index(
    db: DbSession,
    principal: Annotated[Principal, Depends(require_roles([Role.RA, Role.ADMIN]))],
    limit: int = Query(1000, ge=1, le=5000),
) -> dict[str, Any]:
    """Embed every version whose index is missing or built under a different model.

    This is the re-embedding path a model change needs, and it is isolated to this service: nothing
    about swapping the embedding model touches a `regulation` table or a migration.
    """
    from ...celery_app import celery_app

    task = celery_app.send_task("assistant.embed_index", args=[limit], queue="assistant")
    await record(
        db,
        service=SERVICE,
        action="index.rebuild_triggered",
        actor_id=principal.id,
        entity_type="index",
        entity_id=None,
        payload={"task_id": task.id, "limit": limit},
    )
    await db.commit()
    return {
        "code": status.HTTP_202_ACCEPTED,
        "status": "success",
        "message": "Index rebuild enqueued",
        "data": {"task_id": task.id, "limit": limit},
        "meta": None,
    }


@router.get("/index/coverage")
async def index_coverage(db: DbSession, _: CurrentUser) -> dict[str, Any]:
    """How much of the parsed corpus is retrievable, per cell.

    ``versions_unindexed`` is the point. A coverage figure that only counts what *is* indexed cannot
    be told apart from one that indexed everything, and a cell missing half its documents produces
    confident answers from the half it has.
    """
    settings = get_settings()
    rows = list(
        await db.execute(
            text(
                """
                SELECT c.authority::text || '_' || c.domain::text AS cell,
                       count(DISTINCT dv.id)                       AS versions,
                       count(DISTINCT dv.id) FILTER (
                           WHERE EXISTS (SELECT 1 FROM clause_embeddings e
                                         WHERE e.document_version_id = dv.id)
                       )                                           AS versions_indexed,
                       coalesce(sum(emb.passages), 0)              AS passages
                FROM cells c
                JOIN document_cells dc ON dc.cell_id = c.id
                JOIN documents d ON d.id = dc.document_id AND d.doc_type <> 'feed'
                JOIN document_versions dv ON dv.document_id = d.id
                                         AND dv.parser_version IS NOT NULL
                LEFT JOIN LATERAL (
                    SELECT count(*) AS passages FROM clause_embeddings e
                    WHERE e.document_version_id = dv.id
                ) emb ON true
                GROUP BY 1
                ORDER BY 1
                """
            )
        )
    )
    stale = (
        await db.execute(
            text(
                """
                SELECT count(*) FROM clause_embeddings
                WHERE model <> :model OR passage_version <> :passage_version
                """
            ),
            {"model": settings.embedding_model, "passage_version": EMBEDDING_PASSAGE_VERSION},
        )
    ).scalar() or 0

    return ok(
        {
            "model": settings.embedding_model,
            "dim": settings.embedding_dim,
            "passage_version": EMBEDDING_PASSAGE_VERSION,
            "stale_passages": stale,
            "cells": [
                {
                    "cell": row[0],
                    "versions": row[1],
                    "versions_indexed": row[2],
                    "versions_unindexed": row[1] - row[2],
                    "passages": row[3],
                    "complete": row[1] == row[2],
                }
                for row in rows
            ],
        }
    )


__all__ = ["router"]
