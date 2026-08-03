"""The ingestion pipeline: fetch → archive → version, and stop.

Phase 1.0 ends at "bytes are archived and a version row exists." Parsing, clause segmentation and
diffing are phase 1.1; this stage hands off by task name and does not know what happens next.

Each stage is idempotent and independently resumable, and the session is committed **incrementally**
— after the observation, and again after each artefact. A retry therefore skips the artefacts
already versioned rather than redoing the whole fetch, and a crash halfway through a 고시 with four
annexes leaves three of them done rather than none.

The two outcomes that matter for the detection gates:

- ``content_hash`` unchanged → a ``fetch_observation`` and **no** new version. "We looked and
  nothing changed" is a stored fact, which is what makes detection coverage auditable at all
  (ADR-0003 decision 3).
- ``content_hash`` changed → exactly one new ``DocumentVersion``, and downstream work enqueued.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from regops_shared.constants import (
    DriftSignal,
    FetchOutcome,
    StandardStatus,
)
from regops_shared.models import (
    Attachment,
    Document,
    DocumentCell,
    DocumentVersion,
    FetchObservation,
    Source,
    StandardReference,
    StructureDriftAlert,
)
from regops_shared.models.base import utcnow
from regops_shared.storage import archive_bytes

from .connectors import (
    AuthorityError,
    ConnectorError,
    FetchedArtifact,
    FetchResult,
    NonIngestibleSourceError,
    SourceSpec,
    StandardRecord,
    get_connector,
)
from .connectors.law_go_kr import parse_authority_date

log = structlog.get_logger(__name__)

#: Task name phase 1.1 registers. Dispatch is by name only — never import another stage's graph.
PARSE_TASK = "regulation.parse_document_version"


@dataclass(slots=True)
class IngestResult:
    """What one fetch attempt did, for the caller and for the API response."""

    source_slug: str
    outcome: FetchOutcome
    observation_id: uuid.UUID | None = None
    new_version_ids: list[uuid.UUID] = field(default_factory=list)
    unchanged_artifacts: int = 0
    standards_seen: int = 0
    error: str | None = None


def spec_for(source: Source) -> SourceSpec:
    """Project a ``sources`` row down to what a connector is allowed to see."""
    return SourceSpec(
        slug=source.slug,
        title=source.title,
        tier=source.tier,
        ingestible=source.ingestible,
        url_template=source.url_template,
        params=source.params or {},
        http_etag=source.http_etag,
        http_last_modified=source.http_last_modified,
    )


def ingest_source(
    session: Session, source: Source, *, connector_fetcher: object = None
) -> IngestResult:
    """Fetch one source and record what happened, whether or not anything changed."""
    started = utcnow()
    bound = log.bind(source=source.slug)

    if not source.ingestible or not source.connector:
        # Recorded, not skipped silently: "we never look at this source" should be visible in the
        # same place as "we looked and saw nothing."
        observation = _record(
            session,
            source,
            started=started,
            outcome=FetchOutcome.SKIPPED,
            connector_version="-",
            notes="non-ingestible source — no fetch path exists",
        )
        session.commit()
        return IngestResult(source.slug, FetchOutcome.SKIPPED, observation.id)

    connector = get_connector(source.connector, fetcher=connector_fetcher)  # type: ignore[arg-type]

    try:
        fetched = connector.fetch(spec_for(source))
    except NonIngestibleSourceError as exc:
        observation = _record(
            session,
            source,
            started=started,
            outcome=FetchOutcome.SKIPPED,
            connector_version=connector.version,
            notes=str(exc),
        )
        session.commit()
        return IngestResult(source.slug, FetchOutcome.SKIPPED, observation.id, error=str(exc))
    except (AuthorityError, ConnectorError) as exc:
        signal = getattr(exc, "signal", DriftSignal.MISSING_ROOT)
        observation = _record(
            session,
            source,
            started=started,
            outcome=FetchOutcome.ERROR,
            connector_version=connector.version,
            notes=str(exc),
        )
        # Fail closed: raise an operator alert, create no version, emit no change event
        # (ADR-0003 decision 6). A site redesign is not a regulatory amendment.
        session.add(
            StructureDriftAlert(
                source_id=source.id,
                detected_at=utcnow(),
                signal=signal,
                expected=f"{source.connector} artefacts",
                actual=str(exc)[:2000],
            )
        )
        session.commit()
        bound.warning("ingest.failed", signal=signal.value, error=str(exc))
        return IngestResult(source.slug, FetchOutcome.ERROR, observation.id, error=str(exc))

    if fetched.not_modified:
        # A 304 is the cheapest possible observation: the source was proven checked without
        # transferring or hashing anything.
        observation = _record(
            session,
            source,
            started=started,
            outcome=FetchOutcome.NOT_MODIFIED,
            connector_version=connector.version,
            http_status=fetched.http_status,
        )
        session.commit()
        return IngestResult(source.slug, FetchOutcome.NOT_MODIFIED, observation.id)

    _remember_cache_validators(source, fetched)

    observation = _record(
        session,
        source,
        started=started,
        outcome=FetchOutcome.UNCHANGED,  # upgraded below if anything is new
        connector_version=connector.version,
        http_status=fetched.http_status,
        # The body artefact's hash. Recording it makes two observations comparable without
        # joining through versions — which is how "unchanged since T" is answered cheaply.
        content_hash=fetched.artifacts[0].content_hash if fetched.artifacts else None,
        published_at=fetched.published_at,
        artifact_count=len(fetched.artifacts),
    )
    session.commit()

    summary = IngestResult(source.slug, FetchOutcome.UNCHANGED, observation.id)

    for artifact in fetched.artifacts:
        version = _apply_artifact(session, source, artifact, observation)
        if version is None:
            summary.unchanged_artifacts += 1
        else:
            summary.new_version_ids.append(version.id)
        session.commit()  # incremental — a retry resumes here, not at the fetch

    if fetched.standards:
        summary.standards_seen = _apply_standards(session, source, fetched.standards)
        session.commit()

    if summary.new_version_ids:
        observation.outcome = FetchOutcome.CHANGED
        summary.outcome = FetchOutcome.CHANGED
        session.commit()
        for version_id in summary.new_version_ids:
            _enqueue_parse(version_id)

    bound.info(
        "ingest.done",
        outcome=summary.outcome.value,
        new_versions=len(summary.new_version_ids),
        unchanged=summary.unchanged_artifacts,
    )
    return summary


# --- stages ------------------------------------------------------------------------------


def _record(
    session: Session,
    source: Source,
    *,
    started: datetime,
    outcome: FetchOutcome,
    connector_version: str,
    http_status: int | None = None,
    content_hash: str | None = None,
    published_at: datetime | None = None,
    artifact_count: int = 0,
    notes: str | None = None,
) -> FetchObservation:
    """Write the observation. Every attempt gets one, changed or not.

    Note what is *not* passed in: the resolved request URL. There is no column for it, so a
    credential cannot reach the append-only trail even by accident (ADR-0003 decision 13).
    """
    observation = FetchObservation(
        source_id=source.id,
        fetched_at=started,
        http_status=http_status,
        content_hash=content_hash,
        connector_version=connector_version,
        outcome=outcome,
        published_at=published_at,
        artifact_count=artifact_count,
        duration_ms=int((utcnow() - started).total_seconds() * 1000),
        notes=notes,
    )
    session.add(observation)
    session.flush()  # the caller commits
    return observation


def _remember_cache_validators(source: Source, result: FetchResult) -> None:
    if result.etag:
        source.http_etag = result.etag
    if result.last_modified:
        source.http_last_modified = result.last_modified


def _apply_artifact(
    session: Session,
    source: Source,
    artifact: FetchedArtifact,
    observation: FetchObservation,
) -> DocumentVersion | None:
    """Archive and version one artefact. Returns the new version, or None if nothing changed."""
    document = _upsert_document(session, source, artifact)
    _claim_for_cell(session, document, source.cell_id)

    content_hash = artifact.content_hash
    existing = session.scalar(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document.id,
            DocumentVersion.language == artifact.language,
            DocumentVersion.content_hash == content_hash,
        )
    )
    if existing is not None:
        return None

    # Archive the raw response unmodified — this is what gets cited. Content-addressed, so an
    # artefact sharing a response with its annexes resolves to the object already there.
    raw_object_key, _ = archive_bytes(artifact.raw, content_type=artifact.content_type)

    version = DocumentVersion(
        document_id=document.id,
        version_group_id=_version_group_for(session, document, artifact.language),
        version_label=artifact.version_label,
        language=artifact.language,
        content_hash=content_hash,
        raw_object_key=raw_object_key,
        raw_bytes=len(artifact.raw),
        content_type=artifact.content_type,
        retrieved_at=observation.fetched_at,
        published_at=artifact.published_at,
        # effective_date and effective_date_phrase stay null: they are parse outputs, written by
        # phase 1.1 (ADR-0003 decision 5, ADR-0013).
        fetch_observation_id=observation.id,
    )
    session.add(version)
    session.flush()

    for link in artifact.attachments:
        session.add(
            Attachment(
                document_version_id=version.id,
                kind=link.kind,
                title=link.title,
                ordinal=link.ordinal,
                file_format=link.file_format,
                source_url=link.source_url,
            )
        )
    session.flush()
    return version


def _upsert_document(session: Session, source: Source, artifact: FetchedArtifact) -> Document:
    ref = artifact.ref
    document = session.scalar(select(Document).where(Document.canonical_key == ref.canonical_key))
    if document is not None:
        return document

    parent_id: uuid.UUID | None = None
    if ref.parent_canonical_key:
        parent = session.scalar(
            select(Document).where(Document.canonical_key == ref.parent_canonical_key)
        )
        if parent is None:
            # Body artefacts are yielded before their annexes, so this means the response carried
            # a 별표 with no body — a shape change, not a regulation change.
            raise AuthorityError(
                f"{ref.canonical_key}: annex arrived without its parent body",
                signal=DriftSignal.MISSING_ROOT,
            )
        parent_id = parent.id

    document = Document(
        canonical_key=ref.canonical_key,
        title=ref.title,
        doc_type=ref.doc_type,
        issuing_authority=None,
        parent_document_id=parent_id,
        annex_no=ref.annex_no,
        source_id=source.id,
    )
    session.add(document)
    session.flush()
    return document


def _claim_for_cell(session: Session, document: Document, cell_id: uuid.UUID) -> None:
    """M:N claim (ADR-0002 decision 1) — a document is ingested once and claimed by each cell."""
    claimed = session.get(DocumentCell, (document.id, cell_id))
    if claimed is None:
        session.add(DocumentCell(document_id=document.id, cell_id=cell_id))
        session.flush()


def _version_group_for(session: Session, document: Document, language: str) -> uuid.UUID:
    """Language variants of the same act share a group; diffs are computed within one language.

    Not exercised in Phase 1 — both gated cells are MFDS and Korean-only — but the group has to be
    assigned from the first version or the EU spike would need a backfill.
    """
    existing = session.scalar(
        select(DocumentVersion.version_group_id)
        .where(DocumentVersion.document_id == document.id)
        .order_by(DocumentVersion.retrieved_at)
        .limit(1)
    )
    return existing or uuid.uuid4()


def _apply_standards(session: Session, source: Source, records: tuple[StandardRecord, ...]) -> int:
    """Upsert Tier D recognition records. Metadata only — there is no body-text path here.

    ``last_seen_at`` is the freshness signal: a standard that drops off the recognition list stops
    being refreshed, which is observable without ever fetching the standard.
    """
    now = utcnow()
    for record in records:
        existing = session.scalar(
            select(StandardReference).where(
                StandardReference.number == record.number,
                StandardReference.edition == record.edition,
                StandardReference.recognition_number == record.recognition_number,
            )
        )
        status = _coerce_status(record.status)
        if existing is None:
            session.add(
                StandardReference(
                    number=record.number,
                    edition=record.edition,
                    issuing_body=record.issuing_body,
                    recognition_number=record.recognition_number,
                    title=record.title,
                    effective_date=_coerce_date(record.effective_date),
                    withdrawal_date=_coerce_date(record.withdrawal_date),
                    status=status,
                    official_url=record.official_url,
                    cell_id=source.cell_id,
                    source_id=source.id,
                    last_seen_at=now,
                )
            )
        else:
            existing.status = status
            existing.effective_date = _coerce_date(record.effective_date)
            existing.withdrawal_date = _coerce_date(record.withdrawal_date)
            existing.official_url = record.official_url or existing.official_url
            existing.last_seen_at = now
    session.flush()
    return len(records)


def _coerce_status(value: str) -> StandardStatus:
    try:
        return StandardStatus(value)
    except ValueError:
        return StandardStatus.UNKNOWN


def _coerce_date(value: str | None) -> date | None:
    parsed = parse_authority_date(value)
    return parsed.date() if parsed else None


def _enqueue_parse(version_id: uuid.UUID) -> None:
    """Hand off to phase 1.1 by task name only — never import another stage's task graph."""
    from .celery_app import celery_app

    celery_app.send_task(PARSE_TASK, args=[str(version_id)], queue="regulation")


__all__ = ["PARSE_TASK", "IngestResult", "ingest_source", "spec_for"]
