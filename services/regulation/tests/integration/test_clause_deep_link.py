"""Resolving a clause address to the page that holds it.

    STAGE=test REGOPS_DB_NAME=regops_test docker compose run --rm regulation \
        python -m pytest tests/integration/test_clause_deep_link.py -q

An answer citation names a clause, not a page number, and the largest version in the gated corpus
holds 2,212 clauses across five pages. Without this a "deep link" lands the reader on page one —
a link to the document rather than to the evidence, which is how a citation goes unopened, which is
how the mis-citation hallucination class survives (ADR-0006 decision 5).

Fixtures are built with the **sync** session and the assertions drive the async one through
``asyncio.run``, matching how the endpoint actually reads: the pipeline writes synchronously,
FastAPI reads asynchronously. The tests themselves stay sync because the container runs with
``WORKDIR /app`` and never sees the repo-root ``pytest.ini`` that sets ``asyncio_mode``.
"""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import create_async_engine

from app.api.v1.clauses import _page_of
from app.models import Clause, Document, DocumentVersion
from regops_shared.constants import ClauseKind, DocType
from regops_shared.db import AsyncSession, sync_session
from regops_shared.settings import get_settings

pytestmark = pytest.mark.integration

KEY = "test:deeplink:law"
CLAUSE_COUNT = 25


def _purge(session) -> None:
    ids = list(session.scalars(select(Document.id).where(Document.canonical_key == KEY)))
    if ids:
        versions = list(
            session.scalars(select(DocumentVersion.id).where(DocumentVersion.document_id.in_(ids)))
        )
        if versions:
            session.execute(delete(Clause).where(Clause.document_version_id.in_(versions)))
            session.execute(delete(DocumentVersion).where(DocumentVersion.id.in_(versions)))
        session.execute(delete(Document).where(Document.id.in_(ids)))
    session.commit()


@pytest.fixture
def version_id():
    """One version with enough clauses to span pages at a small page size."""
    with sync_session() as session:
        _purge(session)

        document = Document(canonical_key=KEY, title="딥링크 테스트법", doc_type=DocType.LAW)
        session.add(document)
        session.flush()
        version = DocumentVersion(
            document_id=document.id,
            version_group_id=uuid.uuid4(),
            version_label="v1",
            language="ko",
            content_hash=uuid.uuid4().hex,
            raw_object_key=f"{KEY}/v1",
            raw_bytes=1,
            retrieved_at=datetime.now(UTC),
            parser_version="1.1.0",
        )
        session.add(version)
        session.flush()

        for index in range(1, CLAUSE_COUNT + 1):
            path = f"제{index}조"
            session.add(
                Clause(
                    document_version_id=version.id,
                    clause_path=path,
                    path_segments=[path],
                    level=1,
                    # Ordinals are deliberately sparse. They are a reading order, not a dense index,
                    # so paging by `ordinal // page_size` would be wrong on any real document —
                    # rank has to be *counted*.
                    ordinal=index * 10,
                    kind=ClauseKind.PROSE,
                    text=f"제{index}조 본문",
                    content_hash=hashlib.sha256(path.encode()).hexdigest(),
                )
            )
        session.commit()
        target = version.id

    yield target

    with sync_session() as session:
        _purge(session)


def page_of(version_id, clause_path: str | None, page_size: int) -> int | None:
    """Drive the async endpoint helper from a sync test.

    A **fresh engine per call**, disposed before the loop closes. The shared ``get_engine()`` is
    ``lru_cache``d, and an asyncpg pool cached across ``asyncio.run()`` calls binds to a loop that
    has already closed — the exact hazard ``regops_shared.db`` documents and the reason Celery
    workers use the sync engine. Reusing it here fails on the second assertion with
    ``RuntimeError: Event loop is closed``.
    """

    async def run() -> int | None:
        engine = create_async_engine(get_settings().database_url)
        try:
            async with AsyncSession(engine) as db:
                return await _page_of(
                    db, version_id=version_id, clause_path=clause_path, page_size=page_size
                )
        finally:
            await engine.dispose()

    return asyncio.run(run())


def test_a_clause_resolves_to_the_page_that_holds_it(version_id) -> None:
    # 10 per page: 제1조–제10조 on page 1, 제11조–제20조 on page 2, the rest on page 3.
    assert page_of(version_id, "제1조", 10) == 1
    assert page_of(version_id, "제10조", 10) == 1
    assert page_of(version_id, "제11조", 10) == 2
    assert page_of(version_id, "제25조", 10) == 3


def test_rank_is_counted_not_derived_from_the_ordinal(version_id) -> None:
    """Ordinals are sparse — dividing one by the page size would send the reader past the end."""
    assert page_of(version_id, "제25조", 100) == 1


def test_an_unresolvable_path_returns_none(version_id) -> None:
    """A citation into another version. Page 1 plus a "not here" notice beats a silent scroll."""
    assert page_of(version_id, "제999조", 10) is None
    assert page_of(version_id, None, 10) is None
