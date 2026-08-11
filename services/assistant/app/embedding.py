"""The embedding pipeline — deterministic, resumable, and owned by `assistant`.

A pipeline, not an agent (ADR-0008): it calls a model, but the model returns a vector rather than a
judgement, nothing downstream has to gate its output, and the same passage always produces the same
row. The three tests for "agent" want *all* of invokes-an-LLM, writes-provenance, needs-a-check;
this one fails the third.

Two properties make a model swap cheap, which is the whole reason the index lives here rather than
beside the clauses (CLAUDE.md § Architecture rules — LLMs are replaceable, the knowledge graph is
the asset):

- **Every row records the model and the passage version it was built under.** Re-embedding is then
  a query, not a guess: anything not matching the current pair is stale by definition.
- **Re-running over an unchanged version costs no inference.** The passage's ``content_hash`` is
  compared first, so a re-run after a parser improvement re-embeds only what actually changed.

Embeddings stay pinned to Ollama ``nomic-embed-text`` at 768 dimensions regardless of the generation
provider (ADR-0005 decision 7): changing them invalidates the entire index, so they are not a
per-provider choice.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field

import structlog
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from regops_shared.constants import (
    EMBEDDING_COMMIT_EVERY,
    EMBEDDING_PASSAGE_VERSION,
)
from regops_shared.llm import LLMClient, get_llm_client

from .models import ClauseEmbedding
from .passages import Passage, build_passages
from .store import load_clauses, version_meta

log = structlog.get_logger(__name__)


@dataclass(slots=True)
class EmbeddingResult:
    """What one pass over one version produced, and what it was able to skip."""

    document_version_id: uuid.UUID
    passages: int = 0
    embedded: int = 0
    reused: int = 0
    removed: int = 0
    #: Passages the model refused or returned a wrong-width vector for. Counted, never written:
    #: a row whose vector is the wrong dimension breaks the index for every other query.
    failed: int = 0
    error: str | None = None
    scopes: dict[str, int] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.error is None


def embed_version(
    session: Session, version_id: uuid.UUID, *, client: LLMClient | None = None
) -> EmbeddingResult:
    """Build and store every passage vector for one version. Commits incrementally."""
    result = EmbeddingResult(document_version_id=version_id)

    meta = version_meta(session, version_id)
    if meta is None:
        result.error = "unknown version"
        return result

    clauses = load_clauses(session, version_id)
    if not clauses:
        # A feed, or a version that was never parsed. Not an error, and not something to record as
        # covered — an empty index entry would read as "embedded" to the coverage query.
        log.info("embed.no_clauses", version=str(version_id))
        return result

    passages = build_passages(clauses, document_title=meta.document_title)
    result.passages = len(passages)
    for passage in passages:
        result.scopes[passage.scope.value] = result.scopes.get(passage.scope.value, 0) + 1

    client = client or get_llm_client()
    existing = {
        (row.clause_id, row.fragment_index): row
        for row in session.scalars(
            select(ClauseEmbedding).where(ClauseEmbedding.document_version_id == version_id)
        )
    }

    bound = log.bind(version=str(version_id), passages=len(passages))
    try:
        for index, passage in enumerate(passages, start=1):
            _store(
                session,
                passage,
                version_id=version_id,
                client=client,
                existing=existing,
                result=result,
            )
            if index % EMBEDDING_COMMIT_EVERY == 0:
                session.commit()
        result.removed = _prune(session, version_id=version_id, passages=passages)
        session.commit()
    except Exception as exc:
        result.error = str(exc)
        bound.error("embed.failed", error=str(exc))
        raise

    bound.info(
        "embed.done",
        embedded=result.embedded,
        reused=result.reused,
        removed=result.removed,
        failed=result.failed,
    )
    return result


def _store(
    session: Session,
    passage: Passage,
    *,
    version_id: uuid.UUID,
    client: LLMClient,
    existing: dict[tuple[uuid.UUID, int], ClauseEmbedding],
    result: EmbeddingResult,
) -> None:
    key = (passage.clause_id, passage.fragment_index)
    row = existing.get(key)
    content_hash = passage.content_hash

    if (
        row is not None
        and row.content_hash == content_hash
        and row.model == client_embedding_model(client)
        and row.passage_version == EMBEDDING_PASSAGE_VERSION
    ):
        result.reused += 1
        return

    vector = embed_text(client, passage.text)
    if not vector:
        result.failed += 1
        log.warning("embed.empty_vector", clause_path=passage.clause_path)
        return

    if row is None:
        row = ClauseEmbedding(clause_id=passage.clause_id, fragment_index=passage.fragment_index)
        session.add(row)
        existing[key] = row

    row.document_version_id = version_id
    row.scope = passage.scope
    row.passage = passage.text
    row.child_clause_paths = list(passage.child_clause_paths)
    row.content_hash = content_hash
    row.embedding = vector
    row.model = client_embedding_model(client)
    row.dim = len(vector)
    row.passage_version = EMBEDDING_PASSAGE_VERSION
    result.embedded += 1


def embed_text(client: LLMClient, value: str) -> list[float]:
    """One embedding call. Synchronous, because Celery workers are.

    ``asyncio.run`` per call rather than one long-lived loop, for the same reason the extraction
    agent does it: a prefork worker has no event loop of its own, and an HTTP client cached across
    ``asyncio.run()`` calls binds to a loop that has already closed.
    """
    return asyncio.run(client.embed(value))


def client_embedding_model(client: LLMClient) -> str:
    """The embedding model's name, which is not the generation model's.

    ``LLMClient.model`` names what *generates*; embeddings are pinned to Ollama regardless of
    provider, so recording ``client.model`` here would label a Claude-generated deployment's vectors
    with a model that never produced one.
    """
    settings_model = getattr(client, "_embedding_model", None)
    if isinstance(settings_model, str) and settings_model:
        return settings_model
    from regops_shared.settings import get_settings

    return get_settings().embedding_model


def _prune(session: Session, *, version_id: uuid.UUID, passages: list[Passage]) -> int:
    """Drop rows for passages this version no longer has.

    A re-parse can merge two articles or renumber a fragment out of existence. Leaving the old
    vector behind would keep a passage retrievable that the current version does not contain — a
    citation to text that is no longer there, which is the exact failure the version-pinning rule
    exists to prevent.
    """
    keep = {(passage.clause_id, passage.fragment_index) for passage in passages}
    rows = list(
        session.scalars(
            select(ClauseEmbedding).where(ClauseEmbedding.document_version_id == version_id)
        )
    )
    doomed = [row.id for row in rows if (row.clause_id, row.fragment_index) not in keep]
    if not doomed:
        return 0
    session.execute(delete(ClauseEmbedding).where(ClauseEmbedding.id.in_(doomed)))
    return len(doomed)


def stale_versions(session: Session, *, model: str, limit: int = 1000) -> list[uuid.UUID]:
    """Versions whose index does not match the current model or passage rules.

    This is the re-embedding path, and it is deliberately a *query* rather than a stored flag: a
    flag would have to be set by whoever changed the model, and the one thing a model swap reliably
    forgets is the bookkeeping. Includes parsed versions with no index at all, so a newly ingested
    version is picked up by the same sweep.
    """
    rows = session.execute(
        text(
            """
            SELECT dv.id
            FROM document_versions dv
            JOIN documents d ON d.id = dv.document_id
            WHERE dv.parser_version IS NOT NULL
              AND d.doc_type <> 'feed'
              AND (
                    NOT EXISTS (SELECT 1 FROM clause_embeddings e
                                WHERE e.document_version_id = dv.id)
                 OR EXISTS (SELECT 1 FROM clause_embeddings e
                            WHERE e.document_version_id = dv.id
                              AND (e.model <> :model OR e.passage_version <> :passage_version))
              )
            ORDER BY dv.retrieved_at DESC
            LIMIT :limit
            """
        ),
        {"model": model, "passage_version": EMBEDDING_PASSAGE_VERSION, "limit": limit},
    ).all()
    return [row[0] for row in rows]


__all__ = [
    "EmbeddingResult",
    "client_embedding_model",
    "embed_text",
    "embed_version",
    "stale_versions",
]
