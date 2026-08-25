"""Phase 1.0 acceptance criteria, against the real stack.

    docker compose --profile app up -d
    docker compose run --rm migrate
    python -m pytest services/regulation/tests/integration -q

Real Postgres and real MinIO; the *network* is stubbed, because the criteria are about what the
pipeline does with a response, not about whether law.go.kr is reachable from CI. A live-key run is
a separate, manual check — see the phase plan.
"""

from __future__ import annotations

import uuid

import pytest
from helpers import StubFetcher, fixture_bytes
from sqlalchemy import delete, select

from app.ingest import ingest_source
from app.models import (
    Cell,
    Document,
    DocumentCell,
    DocumentVersion,
    FetchObservation,
    Source,
)
from regops_shared.constants import DocType, FetchOutcome, SourceBlock, SourceTier
from regops_shared.db import sync_session
from regops_shared.storage import read_archived

pytestmark = pytest.mark.integration

PARENT_KEY = "mfds:admrul:2100000276068"
TEST_SLUG = "test.integration.cosmetic_safety_standards"
TIER_D_SLUG = "test.integration.tier_d"
#: A second cell subscribing to the *same* upstream instrument. See the shared-document test.
SHARED_SLUG = "test.integration.shared_across_cells"


def _purge(session) -> None:
    documents = list(
        session.scalars(select(Document).where(Document.canonical_key.startswith(PARENT_KEY)))
    )
    ids = [d.id for d in documents]
    if ids:
        session.execute(delete(DocumentCell).where(DocumentCell.document_id.in_(ids)))
        session.execute(delete(DocumentVersion).where(DocumentVersion.document_id.in_(ids)))
        # Children first: annexes reference the body through parent_document_id.
        session.execute(delete(Document).where(Document.parent_document_id.in_(ids)))
        session.execute(delete(Document).where(Document.id.in_(ids)))

    sources = list(
        session.scalars(
            select(Source).where(Source.slug.in_([TEST_SLUG, TIER_D_SLUG, SHARED_SLUG]))
        )
    )
    for source in sources:
        session.execute(delete(FetchObservation).where(FetchObservation.source_id == source.id))
        session.execute(delete(Source).where(Source.id == source.id))
    session.commit()


@pytest.fixture
def session():
    with sync_session() as db:
        _purge(db)
        yield db
        _purge(db)


@pytest.fixture
def cell_id(session) -> uuid.UUID:
    cell = session.scalar(select(Cell).where(Cell.slug == "mfds_cosmetic"))
    assert cell is not None, "migration 0001 seeds the 8 cells"
    return cell.id


@pytest.fixture
def source(session, cell_id: uuid.UUID) -> Source:
    row = Source(
        slug=TEST_SLUG,
        cell_id=cell_id,
        block=SourceBlock.STANDARDS,
        ordinal=99,
        title="화장품 안전기준 등에 관한 규정 (integration fixture)",
        # No {OC}: the network is stubbed, so no credential is resolved and none could leak.
        url_template="https://example.invalid/admrul",
        tier=SourceTier.A,
        ingestible=True,
        connector="law_go_kr_admrul",
        params={},
    )
    session.add(row)
    session.commit()
    return row


def _ingest(session, source: Source, fixture: str):
    return ingest_source(
        session, source, connector_fetcher=StubFetcher(body=fixture_bytes(fixture))
    )


# --- a changed source produces exactly one new version per changed artefact ----


def test_first_fetch_versions_the_body_and_each_annex(session, source: Source) -> None:
    result = _ingest(session, source, "admrul_cosmetic_safety.xml")

    assert result.outcome is FetchOutcome.CHANGED
    assert len(result.new_version_ids) == 3, "one body + two 별표"

    documents = list(
        session.scalars(select(Document).where(Document.canonical_key.startswith(PARENT_KEY)))
    )
    assert len(documents) == 3
    bodies = [d for d in documents if d.parent_document_id is None]
    annexes = [d for d in documents if d.parent_document_id is not None]
    assert len(bodies) == 1 and len(annexes) == 2
    assert all(d.doc_type is DocType.ANNEX for d in annexes)
    assert {d.annex_no for d in annexes} == {"1", "2"}


def test_document_is_claimed_by_the_cell(session, source: Source, cell_id: uuid.UUID) -> None:
    """M:N claim (ADR-0002 decision 1) — a document is ingested once and claimed, not duplicated."""
    _ingest(session, source, "admrul_cosmetic_safety.xml")
    body = session.scalar(select(Document).where(Document.canonical_key == PARENT_KEY))
    claims = list(session.scalars(select(DocumentCell).where(DocumentCell.document_id == body.id)))
    assert [c.cell_id for c in claims] == [cell_id]


def test_a_shared_document_is_claimed_by_every_cell_even_when_the_fetch_is_a_304(
    session, source: Source, cell_id: uuid.UUID
) -> None:
    """A cell's claim must not depend on HTTP cache state.

    Two cells subscribing to one instrument is the M:N case ADR-0002 decision 1 exists for, and
    until ``_reclaim_from_history`` it had a hole: the claim is written in ``_apply_artifact``,
    which a 304 never reaches. So a cell that lost its claim once could never regain it while the
    source kept answering *not modified*.

    Not hypothetical — measured on 2026-08-25. Both FDA cells fetched the FD&C Act in the same
    second; one committed the document and its claim, the other lost the claim to the race and
    thereafter answered 304. The USC is republished annually against a weekly poll, so that cell
    would have shown no claim on its own governing statute for a year, and its coverage denominator
    would have been wrong the whole time.

    The sequence below is that incident: both cells ingest, one claim is removed to model the lost
    race, and the next poll — a 304, carrying no body at all — puts it back.
    """
    other_cell = session.scalar(select(Cell).where(Cell.slug == "mfds_samd"))
    assert other_cell is not None
    shared = Source(
        slug=SHARED_SLUG,
        cell_id=other_cell.id,
        block=SourceBlock.STANDARDS,
        ordinal=98,
        title="The same 고시, claimed by the other gated cell",
        url_template="https://example.invalid/admrul",
        tier=SourceTier.A,
        ingestible=True,
        connector="law_go_kr_admrul",
        params={},
    )
    session.add(shared)
    session.commit()

    _ingest(session, source, "admrul_cosmetic_safety.xml")
    _ingest(session, shared, "admrul_cosmetic_safety.xml")

    body = session.scalar(select(Document).where(Document.canonical_key == PARENT_KEY))
    claimed = {
        c.cell_id
        for c in session.scalars(select(DocumentCell).where(DocumentCell.document_id == body.id))
    }
    assert claimed == {cell_id, other_cell.id}, "both cells claim the one document"

    # Model the lost race: the second cell's claim disappears, and the source keeps 304ing.
    session.execute(
        delete(DocumentCell).where(
            DocumentCell.document_id == body.id, DocumentCell.cell_id == other_cell.id
        )
    )
    session.commit()

    result = ingest_source(session, shared, connector_fetcher=StubFetcher(status=304))
    assert result.outcome is FetchOutcome.NOT_MODIFIED

    recovered = {
        c.cell_id
        for c in session.scalars(select(DocumentCell).where(DocumentCell.document_id == body.id))
    }
    assert recovered == {cell_id, other_cell.id}, "the 304 poll restored the lost claim"


# --- an unchanged re-fetch records an observation and creates NO version -------


def test_unchanged_refetch_creates_no_version(session, source: Source) -> None:
    """The criterion that makes detection coverage auditable: 'we looked and nothing changed' has
    to be a stored fact, and it must not churn versions to become one."""
    _ingest(session, source, "admrul_cosmetic_safety.xml")
    before = _version_count(session)

    result = _ingest(session, source, "admrul_cosmetic_safety.xml")

    assert result.outcome is FetchOutcome.UNCHANGED
    assert result.new_version_ids == []
    assert result.unchanged_artifacts == 3
    assert _version_count(session) == before


def test_every_attempt_is_observed_including_the_unchanged_one(session, source: Source) -> None:
    _ingest(session, source, "admrul_cosmetic_safety.xml")
    _ingest(session, source, "admrul_cosmetic_safety.xml")

    observations = list(
        session.scalars(
            select(FetchObservation)
            .where(FetchObservation.source_id == source.id)
            .order_by(FetchObservation.fetched_at)
        )
    )
    assert len(observations) == 2
    assert [o.outcome for o in observations] == [FetchOutcome.CHANGED, FetchOutcome.UNCHANGED]
    assert all(o.content_hash for o in observations)
    assert all(o.connector_version for o in observations)


# --- annexes version independently (ADR-0012) ---------------------------------


def test_amending_one_annex_versions_only_that_annex(session, source: Source) -> None:
    """The phase 1.0 acceptance criterion: amending 별표 2 alone creates a version for the annex
    and not the body. Most `mfds_cosmetic` obligations live in these annexes, so sharing the
    body's hash would silently miss every ingredient-list amendment."""
    _ingest(session, source, "admrul_cosmetic_safety.xml")
    result = _ingest(session, source, "admrul_cosmetic_safety_annex2_amended.xml")

    assert result.outcome is FetchOutcome.CHANGED
    assert len(result.new_version_ids) == 1, "exactly one new version"

    body = session.scalar(select(Document).where(Document.canonical_key == PARENT_KEY))
    annex1 = session.scalar(select(Document).where(Document.canonical_key == f"{PARENT_KEY}#별표1"))
    annex2 = session.scalar(select(Document).where(Document.canonical_key == f"{PARENT_KEY}#별표2"))

    assert _versions_of(session, body.id) == 1
    assert _versions_of(session, annex1.id) == 1
    assert _versions_of(session, annex2.id) == 2

    new_version = session.get(DocumentVersion, result.new_version_ids[0])
    assert new_version.document_id == annex2.id


# --- WORM archive -------------------------------------------------------------


def test_raw_response_is_archived_unmodified_and_content_addressed(session, source: Source) -> None:
    _ingest(session, source, "admrul_cosmetic_safety.xml")
    versions = list(session.scalars(select(DocumentVersion)))
    version = next(v for v in versions if v.id)

    stored = read_archived(version.raw_object_key)
    assert stored == fixture_bytes("admrul_cosmetic_safety.xml")
    assert version.raw_object_key.endswith(version.raw_object_key.rsplit("/", 1)[-1])
    assert len(version.raw_object_key.rsplit("/", 1)[-1]) == 64, "the key is the sha256 digest"


def test_artifacts_from_one_response_share_the_archived_object(session, source: Source) -> None:
    """Content-addressed storage means the body and its annexes resolve to one object, not three
    copies of a 984 KB response."""
    _ingest(session, source, "admrul_cosmetic_safety.xml")
    keys = {
        v.raw_object_key
        for v in session.scalars(select(DocumentVersion))
        if v.content_type == "application/xml"
    }
    assert len(keys) == 1


# --- Tier D has no fetch path -------------------------------------------------


def test_tier_d_source_is_skipped_and_writes_nothing(session, cell_id: uuid.UUID) -> None:
    row = Source(
        slug=TIER_D_SLUG,
        cell_id=cell_id,
        block=SourceBlock.STANDARDS,
        ordinal=98,
        title="Tier D recognition record (integration fixture)",
        url_template=None,
        tier=SourceTier.D,
        ingestible=False,
        connector=None,
        params={},
    )
    session.add(row)
    session.commit()

    before = _version_count(session)
    result = ingest_source(session, row)

    assert result.outcome is FetchOutcome.SKIPPED
    assert result.new_version_ids == []
    assert _version_count(session) == before

    observation = session.scalar(
        select(FetchObservation).where(FetchObservation.source_id == row.id)
    )
    assert observation is not None, "a skip is recorded, not silent"
    assert observation.outcome is FetchOutcome.SKIPPED


# --- helpers ------------------------------------------------------------------


def _version_count(session) -> int:
    return len(list(session.scalars(select(DocumentVersion))))


def _versions_of(session, document_id: uuid.UUID) -> int:
    return len(
        list(
            session.scalars(
                select(DocumentVersion).where(DocumentVersion.document_id == document_id)
            )
        )
    )
