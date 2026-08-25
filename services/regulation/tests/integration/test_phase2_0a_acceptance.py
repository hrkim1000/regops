"""Phase 2.0a acceptance criteria, against the real stack.

    docker compose --profile app up -d
    docker compose run --rm migrate
    STAGE=test REGOPS_DB_NAME=regops_test docker compose run --rm regulation \
        python -m pytest tests/integration -q

Real Postgres and real MinIO; the network is stubbed. What is **not** stubbed is the shape of the
thing under test: the FD&C Act arrives here the way it arrives in production — through two
independent sources in two different cells, resolving to one `canonical_key`.

That distinction is the whole point of these tests. Phase 1.1 already proves the diff stage fans
out to every claiming cell, but it does so against a fixture that *hands* both claims to one
version, because the gated MFDS pair share no regulation
([test_phase1_1_acceptance.py](test_phase1_1_acceptance.py) says so in as many words). The claim
path is where the defect was — see [phase2.0a](../../../../docs/plan/phase2.0a_fda.md)
*Deviations* 23 — so it is the path these exercise.

Each test names the criterion it covers from
[phase2.0a](../../../../docs/plan/phase2.0a_fda.md) § Acceptance criteria.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select

from app.connectors.http import HttpResponse
from app.diff import diff_version
from app.ingest import ingest_source
from app.models import (
    Cell,
    ChangeEvent,
    Clause,
    ClauseDiff,
    Document,
    DocumentCell,
    DocumentVersion,
    FetchObservation,
    Source,
)
from app.parse import parse_version
from regops_shared.constants import DocType, FetchOutcome, SourceBlock, SourceTier
from regops_shared.db import sync_session

pytestmark = pytest.mark.integration

CANONICAL_KEY = "fda:usc:21-9"
SLUGS = ("test.integration.fda_samd_usc", "test.integration.fda_cosmetic_usc")

EDITION_YEAR = datetime.now(tz=UTC).year - 1
EDITION = f"USCODE-{EDITION_YEAR}-title21"

SUMMARY = json.dumps({"dateIssued": f"{EDITION_YEAR}-12-31", "packageId": EDITION}).encode()


def _granule(heading: str) -> bytes:
    """A USC chapter granule, cut to two sections. The shape is the live one, not the size."""
    return (
        "<html><body>"
        '<p class="subchapter-head">SUBCHAPTER V - DRUGS AND DEVICES</p>'
        '<p class="part-head">Part A - Drugs and Devices</p>'
        '<h3 class="section-head">&sect;351. Adulterated drugs and devices</h3>'
        f'<p class="statutory-body">(a) {heading}</p>'
        '<p class="statutory-body">(1) If it consists in part of any filthy substance.</p>'
        '<p class="source-credit">(June 25, 1938, ch. 675, &sect;501, 52 Stat. 1049.)</p>'
        '<h3 class="section-head">&sect;352. Misbranded drugs and devices</h3>'
        '<p class="statutory-body">(a) False or misleading label.</p>'
        "</body></html>"
    ).encode()


class _GovInfoFetcher:
    """Serves the summary and the granule by URL, as api.govinfo.gov does."""

    def __init__(self, granule: bytes) -> None:
        self._granule = granule

    def get(self, url, *, etag=None, last_modified=None, extra_headers=None) -> HttpResponse:
        if "/summary" in url:
            published = f"USCODE-{EDITION_YEAR}-" in url
            if not published:
                return HttpResponse(status=404, body=b"{}", content_type="application/json")
            return HttpResponse(status=200, body=SUMMARY, content_type="application/json")
        return HttpResponse(status=200, body=self._granule, content_type="text/html")

    def close(self) -> None:  # pragma: no cover - nothing to release
        pass


def _purge(session) -> None:
    documents = list(
        session.scalars(select(Document).where(Document.canonical_key == CANONICAL_KEY))
    )
    ids = [d.id for d in documents]
    if ids:
        versions = list(
            session.scalars(select(DocumentVersion.id).where(DocumentVersion.document_id.in_(ids)))
        )
        if versions:
            # FK order, innermost first. Nothing here extracts, so there are no IRs to unpick.
            diffs = select(ClauseDiff.id).where(ClauseDiff.to_version_id.in_(versions))
            session.execute(delete(ChangeEvent).where(ChangeEvent.clause_diff_id.in_(diffs)))
            session.execute(delete(ClauseDiff).where(ClauseDiff.to_version_id.in_(versions)))
            session.execute(delete(ClauseDiff).where(ClauseDiff.from_version_id.in_(versions)))
            session.execute(delete(Clause).where(Clause.document_version_id.in_(versions)))
        session.execute(delete(DocumentCell).where(DocumentCell.document_id.in_(ids)))
        session.execute(delete(DocumentVersion).where(DocumentVersion.document_id.in_(ids)))
        session.execute(delete(Document).where(Document.id.in_(ids)))

    sources = list(session.scalars(select(Source).where(Source.slug.in_(SLUGS))))
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
def cells(session) -> dict[str, uuid.UUID]:
    rows = session.scalars(select(Cell)).all()
    return {cell.slug: cell.id for cell in rows}


@pytest.fixture
def sources(session, cells) -> list[Source]:
    """One source per FDA cell, both pointing at 21 U.S.C. chapter 9 — the seeded shape."""
    rows = [
        Source(
            slug=slug,
            cell_id=cells[cell],
            block=SourceBlock.PRIMARY_LAWS,
            ordinal=90,
            title="21 U.S.C. chapter 9 — Federal Food, Drug, and Cosmetic Act",
            url_template=None,
            tier=SourceTier.A,
            ingestible=True,
            connector="govinfo_uscode",
            params={"title": "21", "chapter": "9"},
        )
        for slug, cell in zip(SLUGS, ("fda_samd", "fda_cosmetic"), strict=True)
    ]
    session.add_all(rows)
    session.commit()
    return rows


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    """A credential shape, never a real key — and the connector must not reach settings here."""
    from app.connectors import govinfo

    monkeypatch.setattr(govinfo, "_auth_headers", lambda slug: {"X-Api-Key": "not-a-real-key"})


def _ingest(session, source: Source, granule: bytes):
    return ingest_source(session, source, connector_fetcher=_GovInfoFetcher(granule))


# --- criterion: the FD&C Act is ONE Document with two document_cells rows ----------------------


def test_two_cells_two_sources_one_document(session, sources, cells) -> None:
    """*The FD&C Act exists as one `Document` with two `document_cells` rows.*

    Both sources carry the same params, so both resolve to ``fda:usc:21-9``. Two Documents here
    would be the duplicate ADR-0002 decision 1 exists to prevent, and it would show up as two
    separate coverage denominators for one Act.
    """
    first = _ingest(session, sources[0], _granule("Poisonous ingredients"))
    second = _ingest(session, sources[1], _granule("Poisonous ingredients"))

    assert first.outcome is FetchOutcome.CHANGED
    assert second.outcome is FetchOutcome.UNCHANGED, (
        "the second cell re-fetches, it does not re-version"
    )

    documents = session.scalars(
        select(Document).where(Document.canonical_key == CANONICAL_KEY)
    ).all()
    assert len(documents) == 1
    assert documents[0].doc_type is DocType.CODIFIED_STATUTE

    claims = session.scalars(
        select(DocumentCell).where(DocumentCell.document_id == documents[0].id)
    ).all()
    assert {c.cell_id for c in claims} == {cells["fda_samd"], cells["fda_cosmetic"]}

    versions = session.scalars(
        select(DocumentVersion).where(DocumentVersion.document_id == documents[0].id)
    ).all()
    assert len(versions) == 1, "one Act, one edition, one version — not one per subscribing cell"
    assert versions[0].version_label == EDITION


def test_the_claim_survives_a_304_from_the_second_cell(session, sources, cells) -> None:
    """*Deviations 23* — a cell's claim must not depend on HTTP cache state.

    The second cell's source answers 304 on every poll after the first success. Before
    ``_reclaim_from_history`` that meant a claim lost to a race could never come back, and against
    an annually republished statute "never" was a year.
    """
    _ingest(session, sources[0], _granule("Poisonous ingredients"))
    _ingest(session, sources[1], _granule("Poisonous ingredients"))

    document = session.scalar(select(Document).where(Document.canonical_key == CANONICAL_KEY))
    session.execute(
        delete(DocumentCell).where(
            DocumentCell.document_id == document.id,
            DocumentCell.cell_id == cells["fda_cosmetic"],
        )
    )
    session.commit()

    class _NotModified:
        def get(self, url, *, etag=None, last_modified=None, extra_headers=None):
            if "/summary" in url:
                return HttpResponse(status=200, body=SUMMARY, content_type="application/json")
            return HttpResponse(status=304, body=b"", content_type="")

        def close(self) -> None:  # pragma: no cover
            pass

    result = ingest_source(session, sources[1], connector_fetcher=_NotModified())
    assert result.outcome is FetchOutcome.NOT_MODIFIED

    claims = session.scalars(
        select(DocumentCell).where(DocumentCell.document_id == document.id)
    ).all()
    assert {c.cell_id for c in claims} == {cells["fda_samd"], cells["fda_cosmetic"]}


# --- criterion: fan-out reaches every claiming cell and no others ------------------------------


def test_an_amendment_to_the_shared_act_fans_out_to_both_fda_cells_and_no_others(
    session, sources, cells
) -> None:
    """*Cell isolation extended to the shared document* — one of the five non-negotiable cases.

    Phase 1.1 proves this mechanism against a fixture that hands both claims to one version. Here
    the claims arrive the way they do in production, from two sources in two cells, and the
    amendment is a real re-parse of changed statutory text.
    """
    first = _ingest(session, sources[0], _granule("Poisonous ingredients"))
    _ingest(session, sources[1], _granule("Poisonous ingredients"))

    version = session.get(DocumentVersion, first.new_version_ids[0])
    version.retrieved_at = datetime.now(UTC) - timedelta(days=1)
    session.commit()
    parse_version(session, version)
    diff_version(session, version)

    amended = _ingest(session, sources[0], _granule("Poisonous or insanitary ingredients"))
    assert amended.outcome is FetchOutcome.CHANGED, "changed statutory text must produce a version"

    second = session.get(DocumentVersion, amended.new_version_ids[0])
    parse_version(session, second)
    result = diff_version(session, second)

    diffs = session.scalars(
        select(ClauseDiff.id).where(ClauseDiff.to_version_id == second.id)
    ).all()
    assert diffs, "an amendment produced no diff"

    events = session.scalars(select(ChangeEvent).where(ChangeEvent.clause_diff_id.in_(diffs))).all()
    assert {e.cell_id for e in events} == {cells["fda_samd"], cells["fda_cosmetic"]}
    assert result.change_events == len(diffs) * 2, "exactly one event per (diff, claiming cell)"

    outsiders = {cells[slug] for slug in cells if slug not in {"fda_samd", "fda_cosmetic"}}
    assert not ({e.cell_id for e in events} & outsiders), (
        "an event reached a cell that claims nothing"
    )
