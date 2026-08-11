"""Celery tasks for `assistant`. Queue name = service folder name.

Two kinds of work run here, and both are off the request path for the same reason: they are
model-bound. Embedding a version is one inference per passage; answering a question is one
generation plus one verification per claim. A synchronous endpoint doing either would hold a
connection for as long as Ollama takes.

**Embedding is not chained off the parse stage**, for the reason extraction is not (CLAUDE.md
§ Celery Queue Architecture): the deterministic stages are cheap enough to run on every fetch, and
a model-bound one is not. A first embedding is explicit — the API, or ``assistant.embed_index`` over
the stale set — and the sweep picks up new versions on its next run.

The superseded sweep is the one thing `regulation` reaches into: its diff task dispatches
``assistant.supersede_answer_citations`` **by name**, and this service reads ``clause_diffs``
to flag its own rows. No service imports another's task graph.
"""

from __future__ import annotations

import uuid

import structlog

from regops_shared.db import sync_session
from regops_shared.llm import get_llm_client
from regops_shared.settings import get_settings

from .celery_app import celery_app
from .embedding import embed_version, stale_versions
from .models import Query
from .supersede import supersede_for_version

log = structlog.get_logger(__name__)

QUEUE = "assistant"

#: Dispatched by `regulation`'s diff stage, by name. Declared here because this service owns it;
#: the constant exists so the string is written once on this side of the seam.
SUPERSEDE_TASK = "assistant.supersede_answer_citations"


@celery_app.task(name="assistant.embed_document_version", bind=True, max_retries=0)
def embed_document_version(self, document_version_id: str) -> dict[str, object]:
    """Clauses → passage vectors for one version. Commits incrementally.

    ``max_retries=0`` for the same reason the ingestion tasks use it: the work is resumable by
    design — an unchanged passage is reused rather than re-embedded — so re-running the task is the
    retry, and a blind Celery retry would only re-spend the part that already succeeded.
    """
    version_id = uuid.UUID(document_version_id)
    with sync_session() as session:
        result = embed_version(session, version_id)

    return {
        "document_version_id": document_version_id,
        "status": "embedded" if result.ok else "failed",
        "passages": result.passages,
        "embedded": result.embedded,
        "reused": result.reused,
        "removed": result.removed,
        "failed": result.failed,
        "scopes": result.scopes,
        "error": result.error,
    }


@celery_app.task(name="assistant.embed_index", bind=True, max_retries=0)
def embed_index(self, limit: int = 1000) -> dict[str, object]:
    """Embed every version whose index is missing or built under a different model.

    This is the re-embedding path a model change needs (ADR-0006), and it is deliberately isolated
    to this service: swapping the embedding model touches no `regulation` table and no migration.
    """
    model = get_settings().embedding_model
    with sync_session() as session:
        targets = stale_versions(session, model=model, limit=limit)

    for version_id in targets:
        celery_app.send_task(
            "assistant.embed_document_version", args=[str(version_id)], queue=QUEUE
        )
    log.info("embed_index.dispatched", count=len(targets), model=model)
    return {"model": model, "dispatched": len(targets)}


@celery_app.task(name="assistant.answer_query", bind=True, max_retries=0)
def answer_query(self, query_id: str) -> dict[str, object]:
    """Retrieve → generate → verify → score, for a question the API already recorded.

    The question row exists before this runs, so a caller has an id to poll from the moment it
    asked — and a question that was asked stays on the record even if the model never answers it.
    """
    from .ask import answer_query as run

    with sync_session() as session:
        query = session.get(Query, uuid.UUID(query_id))
        if query is None:
            log.warning("answer.unknown_query", query_id=query_id)
            return {"query_id": query_id, "status": "unknown_query"}
        outcome = run(session, query, client=get_llm_client())

    return {
        "query_id": str(outcome.query_id),
        "answer_id": str(outcome.answer_id),
        "status": outcome.status.value,
        "confidence": outcome.confidence,
        "no_answer_reason": (outcome.no_answer_reason.value if outcome.no_answer_reason else None),
        "straddles_effective_date": outcome.straddles_effective_date,
    }


@celery_app.task(name=SUPERSEDE_TASK, bind=True, max_retries=0)
def supersede_answer_citations(self, document_version_id: str) -> dict[str, object]:
    """An amendment landed: flag the answers whose evidence moved under them."""
    version_id = uuid.UUID(document_version_id)
    with sync_session() as session:
        result = supersede_for_version(session, version_id)
        session.commit()

    return {
        "document_version_id": document_version_id,
        "citations_superseded": result.citations_superseded,
        "answers_superseded": result.answers_superseded,
    }


__all__ = [
    "SUPERSEDE_TASK",
    "answer_query",
    "embed_document_version",
    "embed_index",
    "supersede_answer_citations",
]
