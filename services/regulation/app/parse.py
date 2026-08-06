"""The parse stage: archived bytes → clauses, and stop.

Reads from the **WORM archive, never the network** (ADR-0002 decision 6). That is what makes a
profile improvement a re-run rather than a re-ingestion: bump ``PARSER_VERSION``, re-enqueue, and
every affected version is re-derived without touching a government host (ADR-0015).

Idempotent per ``document_version_id``: a re-parse deletes the clauses it previously wrote and
writes them again. That is a replacement of a *derived artefact*, not a mutation of evidence — the
evidence is the archived bytes and they never change.

**Failing closed.** Structure drift — zero clauses, a clause count that moved beyond the threshold,
an envelope that no longer parses — raises an operator alert, and the version is **removed**
(ADR-0003 decision 6). A site redesign is not a regulatory amendment, and a version that exists
without clauses is worse than no version at all: retrieval would return an empty "current text" and
monitoring would see a document it cannot diff. The archived blob is untouched, so the evidence of
what was fetched survives in the WORM store and in ``fetch_observations``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import structlog
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from regops_shared.constants import (
    CLAUSE_COUNT_DRIFT_RATIO,
    PARSER_VERSION,
    DriftSignal,
)
from regops_shared.models import (
    Clause,
    ClauseDiff,
    Document,
    DocumentVersion,
    FetchObservation,
    StructureDriftAlert,
)
from regops_shared.models.base import utcnow
from regops_shared.storage import read_archived

from .parsing import ParsedDocument, ParseError, is_parseable, parse_document

log = structlog.get_logger(__name__)

#: Task name the diff stage registers. Dispatch is by name only — the stages never import each
#: other's graph, even though both live in `regulation` (ADR-0015).
DIFF_TASK = "regulation.diff_document_version"


@dataclass(slots=True)
class ParseResult:
    """What one parse attempt did, for the caller and for the API response."""

    document_version_id: uuid.UUID
    profile: str = ""
    clauses_written: int = 0
    drift: DriftSignal | None = None
    error: str | None = None
    #: Set when a re-parse invalidated a successor's diff, so the caller can heal the chain.
    successor_to_rediff: uuid.UUID | None = None
    #: The document type yields no clauses (a feed). Not a failure, and not something to diff.
    skipped: bool = False

    @property
    def ok(self) -> bool:
        return self.drift is None and self.error is None


def parse_version(session: Session, version: DocumentVersion) -> ParseResult:
    """Parse one archived version into clauses. Commits; the caller enqueues the diff."""
    document = session.get(Document, version.document_id)
    if document is None:  # pragma: no cover - FK makes this unreachable
        return ParseResult(version.id, error="version has no document")

    bound = log.bind(document=document.canonical_key, version=str(version.id))

    if not is_parseable(document.doc_type):
        # A feed has no clauses by nature — it is a list of announcements, not regulation text.
        # Falling through would hit "no parser profile", which `_fail_closed` treats as drift and
        # answers by **deleting the version**, destroying the archived record of what the board said
        # at time T. Skipping is the correct outcome, and it is not an error.
        bound.info("parse.skipped", doc_type=document.doc_type.value, reason="no clauses to parse")
        return ParseResult(version.id, skipped=True)

    try:
        parsed = parse_document(
            read_archived(version.raw_object_key),
            doc_type=document.doc_type,
            canonical_key=document.canonical_key,
        )
    except ParseError as exc:
        return _fail_closed(session, document, version, signal=exc.signal, reason=str(exc))

    drift = _count_drift(session, document, version, len(parsed.clauses))
    if drift is not None:
        return _fail_closed(session, document, version, signal=drift[0], reason=drift[1])

    successor = successor_version_id(session, version)
    written = _persist(session, version, parsed)
    session.commit()

    bound.info("parse.done", profile=parsed.profile, clauses=written)
    return ParseResult(
        version.id,
        profile=parsed.profile,
        clauses_written=written,
        successor_to_rediff=successor,
    )


# --- persistence ---------------------------------------------------------------------------


def _persist(session: Session, version: DocumentVersion, parsed: ParsedDocument) -> int:
    """Replace this version's clauses, and stamp the version with what produced them."""
    _invalidate_derived(session, version)
    session.execute(delete(Clause).where(Clause.document_version_id == version.id))
    session.flush()

    rows: list[Clause] = []
    for clause in parsed.clauses:
        rows.append(
            Clause(
                document_version_id=version.id,
                clause_path=clause.clause_path,
                path_segments=list(clause.path_segments),
                level=clause.level,
                ordinal=len(rows),
                kind=clause.kind,
                heading=clause.heading,
                text=clause.text,
                row_columns=clause.row_columns,
                effective_date=clause.effective_date,
                effective_date_phrase=clause.effective_date_phrase,
                source_ref=clause.source_ref,
                moved_from_ref=clause.moved_from_ref,
                moved_to_ref=clause.moved_to_ref,
                authority_changed=clause.authority_changed,
                content_hash=clause.content_hash,
            )
        )
    session.add_all(rows)
    session.flush()

    # parent_index is positional in the parse result; resolve it once the rows have ids.
    for clause, row in zip(parsed.clauses, rows, strict=True):
        if clause.parent_index is not None:
            row.parent_clause_id = rows[clause.parent_index].id

    # The version's dates are a parse output even though the value comes from the envelope
    # (ADR-0016 decision 3): one writer, and a bad date is fixed by re-parsing.
    version.effective_date = parsed.effective_date
    version.effective_date_phrase = parsed.effective_date_phrase
    version.parser_version = PARSER_VERSION
    session.flush()
    return len(rows)


def _invalidate_derived(session: Session, version: DocumentVersion) -> int:
    """Drop the diffs derived from this version's clauses, in **both** directions.

    A re-parse replaces the clauses a diff was computed over, and ``clause_diffs`` references them
    ``ON DELETE SET NULL`` — so without this, re-parsing leaves diffs whose ``from_clause_id`` and
    ``to_clause_id`` are null, describing a parse that no longer exists. Observed for real: a
    re-parse of the corpus orphaned 2,373 of them, and every one still had a live ``ChangeEvent``
    hanging off it.

    Both directions matter. Diffs *into* this version are obviously stale; diffs *out of* it — the
    successor's comparison against this one — point at the clauses just deleted and are equally
    dead. ``change_events`` cascade with the diff, which is correct: an event whose evidence has
    been re-derived must be re-derived too, not left pointing at nothing.

    The caller re-enqueues the diff for this version and for its successor, so the chain heals
    rather than simply losing a link (ADR-0015 makes re-parsing a routine operation, and a routine
    operation must not degrade the change history).
    """
    stale = (
        select(ClauseDiff.id)
        .where(
            (ClauseDiff.to_version_id == version.id) | (ClauseDiff.from_version_id == version.id)
        )
        .scalar_subquery()
    )
    removed = session.execute(delete(ClauseDiff).where(ClauseDiff.id.in_(stale))).rowcount or 0
    if removed:
        log.info("parse.invalidated_diffs", version=str(version.id), diffs=removed)
    session.flush()
    return removed


def successor_version_id(session: Session, version: DocumentVersion) -> uuid.UUID | None:
    """The next version of the same document and language, if one has already been parsed.

    Used to heal the diff chain after a re-parse: the successor's diff was computed against the
    clauses this parse just replaced.
    """
    return session.scalar(
        select(DocumentVersion.id)
        .where(
            DocumentVersion.document_id == version.document_id,
            DocumentVersion.language == version.language,
            DocumentVersion.id != version.id,
            DocumentVersion.retrieved_at > version.retrieved_at,
            DocumentVersion.parser_version.is_not(None),
        )
        .order_by(DocumentVersion.retrieved_at)
        .limit(1)
    )


# --- failing closed ------------------------------------------------------------------------


def _count_drift(
    session: Session,
    document: Document,
    version: DocumentVersion,
    count: int,
) -> tuple[DriftSignal, str] | None:
    """Zero clauses, or a count that moved too far from the previous version of this document."""
    if count == 0:
        return (
            DriftSignal.ZERO_CLAUSES,
            f"{document.canonical_key}: parse produced no clauses",
        )

    # Two steps on purpose: "the most recent earlier version" and "how many clauses it has" are
    # different questions, and folding them into one aggregate makes the ORDER BY meaningless.
    previous_id = session.scalar(
        select(DocumentVersion.id)
        .where(
            DocumentVersion.document_id == document.id,
            DocumentVersion.id != version.id,
            DocumentVersion.language == version.language,
            DocumentVersion.retrieved_at < version.retrieved_at,
            DocumentVersion.parser_version.is_not(None),
        )
        .order_by(DocumentVersion.retrieved_at.desc())
        .limit(1)
    )
    if previous_id is None:
        return None  # first version of this document — nothing to compare against

    previous = session.scalar(
        select(func.count(Clause.id)).where(Clause.document_version_id == previous_id)
    )
    if not previous:
        return None

    if abs(count - previous) / previous > CLAUSE_COUNT_DRIFT_RATIO:
        return (
            DriftSignal.CLAUSE_COUNT_DELTA,
            f"{document.canonical_key}: clause count moved {previous} → {count}, beyond the "
            f"{CLAUSE_COUNT_DRIFT_RATIO:.0%} threshold",
        )
    return None


def _fail_closed(
    session: Session,
    document: Document,
    version: DocumentVersion,
    *,
    signal: DriftSignal,
    reason: str,
) -> ParseResult:
    """Raise the operator alert and remove the version. No clauses, no diff, no change event.

    Deleting the version keeps a strong invariant for every downstream reader: **a
    ``DocumentVersion`` that exists has clauses and is citable.** A half-existing version would make
    retrieval answer "current text" with nothing and leave monitoring a document it cannot diff.

    The archived object is *not* removed — it is write-once, and it plus the ``fetch_observation``
    are what prove the fetch happened and what came back.
    """
    source_id = _source_for(session, document, version)
    if source_id is not None:
        _raise_alert(session, source_id, signal=signal, reason=reason, document=document)

    session.execute(delete(Clause).where(Clause.document_version_id == version.id))
    session.delete(version)
    session.commit()

    log.warning(
        "parse.drift",
        document=document.canonical_key,
        signal=signal.value,
        reason=reason,
        version_removed=True,
    )
    return ParseResult(version.id, drift=signal, error=reason)


def _source_for(session: Session, document: Document, version: DocumentVersion) -> uuid.UUID | None:
    """The source to hang the alert on: the one that fetched this version, else the document's."""
    if version.fetch_observation_id:
        observation = session.get(FetchObservation, version.fetch_observation_id)
        if observation is not None:
            return observation.source_id
    return document.source_id


def _raise_alert(
    session: Session,
    source_id: uuid.UUID,
    *,
    signal: DriftSignal,
    reason: str,
    document: Document,
) -> None:
    """One open alert per (source, signal, document).

    Deduped because a permanently broken envelope re-fetches on every poll: the version is removed,
    so the next fetch sees a new ``content_hash``, re-creates it and fails again. Without the dedupe
    that is one new alert per source per day until someone looks, which is how an alert channel gets
    muted.
    """
    existing = session.scalar(
        select(StructureDriftAlert).where(
            StructureDriftAlert.source_id == source_id,
            StructureDriftAlert.signal == signal,
            StructureDriftAlert.resolved_at.is_(None),
            StructureDriftAlert.expected == document.canonical_key,
        )
    )
    if existing is not None:
        existing.actual = reason[:2000]
        existing.detected_at = utcnow()
        return

    session.add(
        StructureDriftAlert(
            source_id=source_id,
            detected_at=utcnow(),
            signal=signal,
            expected=document.canonical_key,
            actual=reason[:2000],
        )
    )


__all__ = ["DIFF_TASK", "ParseResult", "parse_version"]
