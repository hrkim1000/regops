"""Phase 1.4 acceptance criteria, against the real stack.

    docker compose --profile app up -d
    REGOPS_DB_NAME=regops_test docker compose run --rm migrate
    STAGE=test REGOPS_DB_NAME=regops_test docker compose run --rm monitoring \
        python -m pytest tests/integration -q

Real Postgres, real change events, real diffs, real SQL across the seam. There is no LLM in this
pillar at all — routing, grading and delivery are deterministic — so nothing here is stubbed except
the transport, and that only where a test needs a receiver that fails on purpose.

The fixtures import `regulation`'s models directly, which service code may never do. A test is not a
service: it is building the world the service will read, and going through raw SQL to do it would
make the fixture harder to read without making the boundary any more real. The boundary itself is
checked statically in ``tests/unit/test_seam.py``.

Each test names the criterion it covers from
[phase1.4](../../../../docs/plan/phase1.4_monitoring.md) § Acceptance criteria.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import delete, select

from app.delivery import Channel, DeliveryError, InAppChannel, deliver_alert
from app.models import Alert, AlertDelivery, AlertSubscription
from app.routing import route_version
from regops_shared.constants import (
    DELIVERY_MAX_ATTEMPTS,
    DETECTION_LATENCY_TARGET_HOURS,
    AlertChannel,
    AlertSeverity,
    AlertStatus,
    ChangeKind,
    ClauseKind,
    DeliveryStatus,
    DocType,
    Domain,
    IRStatus,
)
from regops_shared.db import sync_session
from regops_shared.models import (
    IR,
    Cell,
    ChangeEvent,
    Clause,
    ClauseDiff,
    Document,
    DocumentCell,
    DocumentVersion,
    IRCitation,
)
from regops_shared.models.base import utcnow

pytestmark = pytest.mark.integration

KEY_PREFIX = "test:phase14"
SUBSCRIBER = uuid.UUID("00000000-0000-4000-8000-0000000014a1")
OTHER_SUBSCRIBER = uuid.UUID("00000000-0000-4000-8000-0000000014a2")


# --- fixtures -----------------------------------------------------------------------------------


def _purge(session) -> None:
    documents = list(
        session.scalars(select(Document).where(Document.canonical_key.startswith(KEY_PREFIX)))
    )
    ids = [row.id for row in documents]
    if ids:
        versions = list(
            session.scalars(select(DocumentVersion.id).where(DocumentVersion.document_id.in_(ids)))
        )
        alerts = list(session.scalars(select(Alert.id).where(Alert.document_id.in_(ids))))
        if alerts:
            session.execute(delete(AlertDelivery).where(AlertDelivery.alert_id.in_(alerts)))
            session.execute(delete(Alert).where(Alert.id.in_(alerts)))
        if versions:
            diffs = list(
                session.scalars(select(ClauseDiff.id).where(ClauseDiff.to_version_id.in_(versions)))
            )
            if diffs:
                session.execute(delete(ChangeEvent).where(ChangeEvent.clause_diff_id.in_(diffs)))
            irs = list(
                session.scalars(
                    select(IRCitation.ir_id).where(IRCitation.document_version_id.in_(versions))
                )
            )
            session.execute(delete(IRCitation).where(IRCitation.document_version_id.in_(versions)))
            if irs:
                session.execute(delete(IR).where(IR.id.in_(irs)))
            session.execute(delete(ClauseDiff).where(ClauseDiff.to_version_id.in_(versions)))
            session.execute(delete(ClauseDiff).where(ClauseDiff.from_version_id.in_(versions)))
            session.execute(delete(Clause).where(Clause.document_version_id.in_(versions)))
        session.execute(delete(DocumentCell).where(DocumentCell.document_id.in_(ids)))
        session.execute(delete(DocumentVersion).where(DocumentVersion.document_id.in_(ids)))
        session.execute(delete(Document).where(Document.id.in_(ids)))

    subscriptions = list(
        session.scalars(
            select(AlertSubscription.id).where(
                AlertSubscription.subscriber_id.in_([SUBSCRIBER, OTHER_SUBSCRIBER])
            )
        )
    )
    if subscriptions:
        session.execute(
            delete(AlertDelivery).where(AlertDelivery.subscription_id.in_(subscriptions))
        )
        session.execute(delete(AlertSubscription).where(AlertSubscription.id.in_(subscriptions)))
    session.commit()


@pytest.fixture
def session():
    with sync_session() as db:
        _purge(db)
        yield db
        _purge(db)


@pytest.fixture
def cells(session) -> dict[str, uuid.UUID]:
    rows = session.scalars(select(Cell).where(Cell.slug.in_(["mfds_cosmetic", "mfds_samd"]))).all()
    assert len(rows) == 2, "migration 0001 seeds the 8 cells"
    return {cell.slug: cell.id for cell in rows}


def _document(session, *, key: str, title: str, cell_ids: list[uuid.UUID]) -> Document:
    document = Document(canonical_key=f"{KEY_PREFIX}:{key}", title=title, doc_type=DocType.LAW)
    session.add(document)
    session.flush()
    for cell_id in cell_ids:
        session.add(DocumentCell(document_id=document.id, cell_id=cell_id))
    return document


def _version(
    session,
    document: Document,
    *,
    label: str,
    published_at: datetime | None = None,
    retrieved_at: datetime | None = None,
    effective: date | None = None,
) -> DocumentVersion:
    version = DocumentVersion(
        document_id=document.id,
        version_group_id=uuid.uuid4(),
        version_label=label,
        language="ko",
        content_hash=uuid.uuid4().hex,
        raw_object_key=f"{KEY_PREFIX}/{label}",
        raw_bytes=1,
        retrieved_at=retrieved_at or utcnow(),
        published_at=published_at,
        effective_date=effective or date(2026, 4, 2),
        parser_version="1.1.0",
    )
    session.add(version)
    session.flush()
    return version


def _clause(session, version: DocumentVersion, *, path: str, text: str, ordinal: int) -> Clause:
    clause = Clause(
        document_version_id=version.id,
        clause_path=path,
        path_segments=path.split("/"),
        level=len(path.split("/")),
        ordinal=ordinal,
        kind=ClauseKind.PROSE,
        text=text,
        content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
    )
    session.add(clause)
    session.flush()
    return clause


def _amend(
    session,
    *,
    previous: DocumentVersion,
    current: DocumentVersion,
    cell_ids: list[uuid.UUID],
    changes: list[tuple[str, ChangeKind]],
    detected_at: datetime | None = None,
) -> list[ChangeEvent]:
    """Write the diffs and fan them out to every claiming cell, exactly as the diff stage does."""
    moment = detected_at or utcnow()
    events: list[ChangeEvent] = []
    for path, kind in changes:
        diff = ClauseDiff(
            from_version_id=previous.id,
            to_version_id=current.id,
            clause_path=path,
            from_clause_path=path if kind in (ChangeKind.RENUMBERED, ChangeKind.MOVED) else None,
            change_kind=kind,
        )
        session.add(diff)
        session.flush()
        for cell_id in cell_ids:
            event = ChangeEvent(
                clause_diff_id=diff.id,
                cell_id=cell_id,
                document_id=current.document_id,
                detected_at=moment,
            )
            session.add(event)
            events.append(event)
    session.flush()
    return events


def _subscribe(
    session,
    *,
    cell_id: uuid.UUID,
    subscriber_id: uuid.UUID = SUBSCRIBER,
    channel: AlertChannel = AlertChannel.IN_APP,
    destination: str | None = None,
    min_severity: AlertSeverity = AlertSeverity.LOW,
) -> AlertSubscription:
    subscription = AlertSubscription(
        subscriber_id=subscriber_id,
        cell_id=cell_id,
        channel=channel,
        destination=destination,
        min_severity=min_severity,
    )
    session.add(subscription)
    session.flush()
    return subscription


@pytest.fixture
def amendment(session, cells):
    """One cosmetic law amended in three clauses, with a subscriber on the cell."""
    document = _document(
        session, key="law", title="테스트 화장품법", cell_ids=[cells["mfds_cosmetic"]]
    )
    first = _version(session, document, label="v1")
    _clause(
        session, first, path="제5조", text="제5조(기록) 기록을 3년간 보관하여야 한다.", ordinal=1
    )
    second = _version(
        session,
        document,
        label="v2",
        published_at=utcnow() - timedelta(hours=2),
        retrieved_at=utcnow() - timedelta(hours=1),
    )
    _clause(
        session, second, path="제5조", text="제5조(기록) 기록을 5년간 보관하여야 한다.", ordinal=1
    )
    _amend(
        session,
        previous=first,
        current=second,
        cell_ids=[cells["mfds_cosmetic"]],
        changes=[
            ("제5조", ChangeKind.MODIFIED),
            ("제6조", ChangeKind.ADDED),
            ("제7조", ChangeKind.MODIFIED),
        ],
    )
    _subscribe(session, cell_id=cells["mfds_cosmetic"])
    session.commit()
    return document, first, second


# --- criterion: publication → alert measured end to end at ≤ 24h ---------------------------------


def test_publication_to_alert_is_measured_and_inside_the_gate(session, amendment) -> None:
    _, _, version = amendment

    result = route_version(session, version.id)

    alert = session.scalar(select(Alert).where(Alert.document_version_id == version.id))
    assert result.alerts_created == 1
    assert alert.published_at is not None
    latency_hours = (alert.created_at - alert.published_at).total_seconds() / 3600
    assert 0 < latency_hours <= DETECTION_LATENCY_TARGET_HOURS


def test_a_source_that_publishes_no_date_is_unmeasurable_never_zero(session, cells) -> None:
    """ADR-0003 decision 5. `retrieved_at` still bounds it; a zero would be a fabricated pass."""
    document = _document(
        session, key="nodate", title="테스트 고시", cell_ids=[cells["mfds_cosmetic"]]
    )
    first = _version(session, document, label="n1")
    second = _version(session, document, label="n2", published_at=None)
    _amend(
        session,
        previous=first,
        current=second,
        cell_ids=[cells["mfds_cosmetic"]],
        changes=[("제1조", ChangeKind.MODIFIED)],
    )
    _subscribe(session, cell_id=cells["mfds_cosmetic"])
    session.commit()

    route_version(session, second.id)

    alert = session.scalar(select(Alert).where(Alert.document_version_id == second.id))
    assert alert.published_at is None
    assert alert.retrieved_at is not None


# --- criterion: every emitted change event reaches an alert (detection coverage) -----------------


def test_every_emitted_event_for_a_subscribed_cell_reaches_the_alert(session, amendment) -> None:
    """Coverage is alerted-over-emitted, and the denominator is the other side of the seam."""
    _, _, version = amendment

    route_version(session, version.id)

    emitted = set(
        session.scalars(
            select(ChangeEvent.id)
            .join(ClauseDiff, ClauseDiff.id == ChangeEvent.clause_diff_id)
            .where(ClauseDiff.to_version_id == version.id)
        )
    )
    alert = session.scalar(select(Alert).where(Alert.document_version_id == version.id))
    assert set(alert.change_event_ids) == emitted


# --- criterion: a renumbering-only change generates no end-user alert -----------------------------


def test_a_renumbering_only_amendment_raises_no_alert_at_all(session, cells) -> None:
    """Not a suppressed row — nothing. A renumber moves an address, not an obligation
    (ADR-0002 decision 7), and false positives attack coverage from the side no gate measures."""
    document = _document(
        session, key="renumber", title="테스트 고시", cell_ids=[cells["mfds_cosmetic"]]
    )
    first = _version(session, document, label="r1")
    second = _version(session, document, label="r2")
    _amend(
        session,
        previous=first,
        current=second,
        cell_ids=[cells["mfds_cosmetic"]],
        changes=[
            ("제7조", ChangeKind.RENUMBERED),
            ("제8조", ChangeKind.RENUMBERED),
            ("제9조", ChangeKind.MOVED),
        ],
    )
    _subscribe(session, cell_id=cells["mfds_cosmetic"])
    session.commit()

    result = route_version(session, second.id)

    assert result.alerts_created == 0
    assert result.cells_suppressed == 1
    assert result.events_suppressed == 3
    assert session.scalar(select(Alert).where(Alert.document_version_id == second.id)) is None


def test_a_renumber_alongside_a_real_edit_is_counted_but_does_not_block_the_alert(
    session, cells
) -> None:
    """Suppression is per-event, not per-amendment: the real edit still has to get through."""
    document = _document(
        session, key="mixed", title="테스트 혼합", cell_ids=[cells["mfds_cosmetic"]]
    )
    first = _version(session, document, label="m1")
    second = _version(session, document, label="m2")
    _amend(
        session,
        previous=first,
        current=second,
        cell_ids=[cells["mfds_cosmetic"]],
        changes=[
            ("제7조", ChangeKind.RENUMBERED),
            ("제5조", ChangeKind.MODIFIED),
        ],
    )
    _subscribe(session, cell_id=cells["mfds_cosmetic"])
    session.commit()

    result = route_version(session, second.id)

    alert = session.scalar(select(Alert).where(Alert.document_version_id == second.id))
    assert result.events_suppressed == 1
    assert alert.clause_count == 1
    assert [ref["clause_path"] for ref in alert.clause_references] == ["제5조"]


# --- criterion: an amendment touching 40 clauses produces one alert, not 40 -----------------------


def test_forty_touched_clauses_produce_one_alert_with_forty_references(session, cells) -> None:
    document = _document(
        session, key="bulk", title="테스트 대량개정", cell_ids=[cells["mfds_cosmetic"]]
    )
    first = _version(session, document, label="b1")
    second = _version(session, document, label="b2")
    _amend(
        session,
        previous=first,
        current=second,
        cell_ids=[cells["mfds_cosmetic"]],
        changes=[(f"제{n}조", ChangeKind.MODIFIED) for n in range(1, 41)],
    )
    _subscribe(session, cell_id=cells["mfds_cosmetic"])
    session.commit()

    route_version(session, second.id)

    alerts = session.scalars(select(Alert).where(Alert.document_version_id == second.id)).all()
    assert len(alerts) == 1
    assert alerts[0].clause_count == 40
    assert len(alerts[0].clause_references) == 40
    # 40 is well past the bulk threshold, so size alone carries it to medium.
    assert alerts[0].severity is AlertSeverity.MEDIUM


def test_re_routing_the_same_amendment_updates_one_alert_rather_than_raising_a_second(
    session, amendment
) -> None:
    """A re-diff is the retry. The (tenant, cell, version) key is what makes it idempotent."""
    _, _, version = amendment

    first = route_version(session, version.id)
    second = route_version(session, version.id)

    assert (first.alerts_created, first.alerts_updated) == (1, 0)
    assert (second.alerts_created, second.alerts_updated) == (0, 1)
    assert (
        session.scalar(
            select(Alert).where(Alert.document_version_id == version.id).order_by(Alert.created_at)
        )
        is not None
    )
    rows = session.scalars(select(Alert).where(Alert.document_version_id == version.id)).all()
    assert len(rows) == 1


def test_re_routing_does_not_unassign_the_owner(session, amendment) -> None:
    """A re-parse that re-derives the same amendment must not lose who was told to deal with it."""
    _, _, version = amendment
    route_version(session, version.id)
    alert = session.scalar(select(Alert).where(Alert.document_version_id == version.id))
    alert.owner_id = SUBSCRIBER
    alert.assigned_at = utcnow()
    session.commit()

    route_version(session, version.id)

    session.refresh(alert)
    assert alert.owner_id == SUBSCRIBER


# --- criterion: fan-out reaches every claiming cell and no others ---------------------------------


def test_a_document_claimed_by_two_cells_alerts_both_and_only_those(session, cells) -> None:
    """One ChangeEvent per claiming cell already; this side must not widen or narrow it."""
    document = _document(
        session,
        key="shared",
        title="인체적용제품 규정",
        cell_ids=[cells["mfds_cosmetic"], cells["mfds_samd"]],
    )
    first = _version(session, document, label="s1")
    second = _version(session, document, label="s2")
    _amend(
        session,
        previous=first,
        current=second,
        cell_ids=[cells["mfds_cosmetic"], cells["mfds_samd"]],
        changes=[("제3조", ChangeKind.MODIFIED)],
    )
    _subscribe(session, cell_id=cells["mfds_cosmetic"])
    _subscribe(session, cell_id=cells["mfds_samd"], subscriber_id=OTHER_SUBSCRIBER)
    session.commit()

    route_version(session, second.id)

    alerts = session.scalars(select(Alert).where(Alert.document_version_id == second.id)).all()
    assert {alert.cell_id for alert in alerts} == {cells["mfds_cosmetic"], cells["mfds_samd"]}


def test_a_cell_nobody_subscribes_to_gets_no_alert(session, cells) -> None:
    """ "and no others" has a second half: an alert with no reader belongs to no tenant."""
    document = _document(
        session,
        key="unsubscribed",
        title="인체적용제품 규정",
        cell_ids=[cells["mfds_cosmetic"], cells["mfds_samd"]],
    )
    first = _version(session, document, label="u1")
    second = _version(session, document, label="u2")
    _amend(
        session,
        previous=first,
        current=second,
        cell_ids=[cells["mfds_cosmetic"], cells["mfds_samd"]],
        changes=[("제3조", ChangeKind.MODIFIED)],
    )
    _subscribe(session, cell_id=cells["mfds_cosmetic"])
    session.commit()

    result = route_version(session, second.id)

    alerts = session.scalars(select(Alert).where(Alert.document_version_id == second.id)).all()
    assert [alert.cell_id for alert in alerts] == [cells["mfds_cosmetic"]]
    assert result.cells_without_subscribers == 1


# --- impact grading -------------------------------------------------------------------------------


def test_an_amendment_under_a_locked_ir_is_graded_high(session, cells) -> None:
    """The strongest grading input Phase 1 has — and it survives the staleness sweep.

    The diff stage moves a locked IR to ``stale`` in the same transaction that supersedes its
    citation, so grading on ``status = 'locked'`` would find nothing. ``locked_at`` is what records
    that a human ever asserted the obligation, and that is the fact worth grading on.
    """
    document = _document(
        session, key="locked", title="테스트 화장품법", cell_ids=[cells["mfds_cosmetic"]]
    )
    first = _version(session, document, label="l1")
    _clause(session, first, path="제5조", text="제5조(기록) 보관하여야 한다.", ordinal=1)
    second = _version(session, document, label="l2")
    events = _amend(
        session,
        previous=first,
        current=second,
        cell_ids=[cells["mfds_cosmetic"]],
        changes=[("제5조", ChangeKind.MODIFIED)],
    )
    diff_id = session.scalar(select(ClauseDiff.id).where(ClauseDiff.to_version_id == second.id))
    ir = IR(
        domain_profile=Domain.COSMETIC,
        statement="제조업자는 기록을 보관하여야 한다.",
        # Locked once, then staled by this very amendment — exactly the state routing reads.
        status=IRStatus.STALE,
        locked_by=SUBSCRIBER,
        locked_at=utcnow() - timedelta(days=1),
        stale_since=utcnow(),
    )
    session.add(ir)
    session.flush()
    session.add(
        IRCitation(
            ir_id=ir.id,
            document_id=document.id,
            document_version_id=first.id,
            clause_path="제5조",
            superseded_at=utcnow(),
            superseded_by_diff_id=diff_id,
        )
    )
    _subscribe(session, cell_id=cells["mfds_cosmetic"])
    session.commit()
    assert events

    route_version(session, second.id)

    alert = session.scalar(select(Alert).where(Alert.document_version_id == second.id))
    assert alert.severity is AlertSeverity.HIGH
    assert alert.cited_by_locked_ir is True
    assert alert.locked_ir_count == 1
    assert "확정(lock)된 요구사항 1건" in alert.summary


def test_a_draft_ir_staled_by_the_same_sweep_does_not_raise_the_grade(session, cells) -> None:
    """A draft is model output nobody has approved. Grading on it would let the extractor decide
    severity, which is the one thing ADR-0004 decision 4 keeps it from doing."""
    document = _document(
        session, key="draft", title="테스트 화장품법", cell_ids=[cells["mfds_cosmetic"]]
    )
    first = _version(session, document, label="d1")
    second = _version(session, document, label="d2")
    _amend(
        session,
        previous=first,
        current=second,
        cell_ids=[cells["mfds_cosmetic"]],
        changes=[("제5조", ChangeKind.MODIFIED)],
    )
    diff_id = session.scalar(select(ClauseDiff.id).where(ClauseDiff.to_version_id == second.id))
    ir = IR(
        domain_profile=Domain.COSMETIC,
        statement="제조업자는 기록을 보관하여야 한다.",
        status=IRStatus.STALE,
        stale_since=utcnow(),
    )
    session.add(ir)
    session.flush()
    session.add(
        IRCitation(
            ir_id=ir.id,
            document_id=document.id,
            document_version_id=first.id,
            clause_path="제5조",
            superseded_at=utcnow(),
            superseded_by_diff_id=diff_id,
        )
    )
    _subscribe(session, cell_id=cells["mfds_cosmetic"])
    session.commit()

    route_version(session, second.id)

    alert = session.scalar(select(Alert).where(Alert.document_version_id == second.id))
    assert alert.locked_ir_count == 0
    assert alert.severity is AlertSeverity.LOW


# --- criterion: delivery failure retries and is visible -------------------------------------------


class _WedgedChannel(Channel):
    """A receiver that is down. Fails a fixed number of times, then starts answering."""

    name = AlertChannel.IN_APP

    def __init__(self, failures: int) -> None:
        self.remaining = failures
        self.calls = 0

    def send(self, *, alert, destination) -> None:
        self.calls += 1
        if self.remaining > 0:
            self.remaining -= 1
            raise DeliveryError("receiver returned HTTP 503")


def test_a_failed_delivery_is_recorded_with_a_reason_and_a_scheduled_retry(
    session, amendment
) -> None:
    _, _, version = amendment
    route_version(session, version.id)
    alert = session.scalar(select(Alert).where(Alert.document_version_id == version.id))

    result = deliver_alert(
        session, alert.id, channels={AlertChannel.IN_APP: _WedgedChannel(failures=1)}
    )

    attempt = session.scalar(select(AlertDelivery).where(AlertDelivery.alert_id == alert.id))
    assert result.failed == 1
    assert result.retry_in_seconds is not None
    assert attempt.status is DeliveryStatus.FAILED
    assert attempt.error and "503" in attempt.error
    assert attempt.next_retry_at is not None
    assert session.get(Alert, alert.id).status is AlertStatus.PENDING


def test_a_receiver_that_recovers_is_delivered_to_and_the_history_shows_both(
    session, amendment
) -> None:
    """ "It failed twice and then succeeded" is the whole content of this criterion, and only an
    append-only attempt log can say it."""
    _, _, version = amendment
    route_version(session, version.id)
    alert = session.scalar(select(Alert).where(Alert.document_version_id == version.id))
    channel = _WedgedChannel(failures=2)

    deliver_alert(session, alert.id, channels={AlertChannel.IN_APP: channel})
    deliver_alert(session, alert.id, channels={AlertChannel.IN_APP: channel})
    result = deliver_alert(session, alert.id, channels={AlertChannel.IN_APP: channel})

    attempts = session.scalars(
        select(AlertDelivery)
        .where(AlertDelivery.alert_id == alert.id)
        .order_by(AlertDelivery.attempt)
    ).all()
    assert [row.status for row in attempts] == [
        DeliveryStatus.FAILED,
        DeliveryStatus.FAILED,
        DeliveryStatus.SENT,
    ]
    assert result.retry_in_seconds is None
    assert session.get(Alert, alert.id).status is AlertStatus.DELIVERED


def test_a_permanently_wedged_receiver_is_abandoned_visibly_not_silently(
    session, amendment
) -> None:
    """A wedged relay must not retry forever, and must not vanish. It ends as a FAILED alert with
    a full attempt history — and it never touched ingestion to get there."""
    _, _, version = amendment
    route_version(session, version.id)
    alert = session.scalar(select(Alert).where(Alert.document_version_id == version.id))
    channel = _WedgedChannel(failures=DELIVERY_MAX_ATTEMPTS + 5)

    for _ in range(DELIVERY_MAX_ATTEMPTS + 2):
        deliver_alert(session, alert.id, channels={AlertChannel.IN_APP: channel})

    attempts = session.scalars(
        select(AlertDelivery).where(AlertDelivery.alert_id == alert.id)
    ).all()
    assert len(attempts) == DELIVERY_MAX_ATTEMPTS
    assert channel.calls == DELIVERY_MAX_ATTEMPTS
    assert session.get(Alert, alert.id).status is AlertStatus.FAILED


def test_a_delivered_subscriber_is_never_told_twice(session, amendment) -> None:
    """Re-running delivery is the retry, so it has to be idempotent per subscriber."""
    _, _, version = amendment
    route_version(session, version.id)
    alert = session.scalar(select(Alert).where(Alert.document_version_id == version.id))
    channel = _WedgedChannel(failures=0)

    deliver_alert(session, alert.id, channels={AlertChannel.IN_APP: channel})
    second = deliver_alert(session, alert.id, channels={AlertChannel.IN_APP: channel})

    assert channel.calls == 1
    assert second.skipped == 1
    assert second.attempted == 0


def test_a_subscriber_below_the_severity_floor_is_not_pushed_but_the_alert_still_exists(
    session, cells
) -> None:
    """``min_severity`` filters *delivery*, not composition: the alert is still readable in the
    list, it is simply not pushed to someone who asked for medium and above."""
    document = _document(
        session, key="floor", title="테스트 고시", cell_ids=[cells["mfds_cosmetic"]]
    )
    first = _version(session, document, label="f1")
    second = _version(session, document, label="f2")
    _amend(
        session,
        previous=first,
        current=second,
        cell_ids=[cells["mfds_cosmetic"]],
        changes=[("제2조", ChangeKind.MODIFIED)],
    )
    _subscribe(session, cell_id=cells["mfds_cosmetic"], min_severity=AlertSeverity.HIGH)
    session.commit()

    route_version(session, second.id)
    alert = session.scalar(select(Alert).where(Alert.document_version_id == second.id))
    result = deliver_alert(session, alert.id, channels={AlertChannel.IN_APP: InAppChannel()})

    assert alert.severity is AlertSeverity.LOW
    assert result.attempted == 0
    assert (
        session.scalars(select(AlertDelivery).where(AlertDelivery.alert_id == alert.id)).all() == []
    )
    # Nothing outstanding, so the alert is not left pending over work nobody will do.
    assert session.get(Alert, alert.id).status is AlertStatus.DELIVERED


def test_delivery_is_recorded_even_when_the_channel_cannot_fail(session, amendment) -> None:
    """ "Delivered in-app at 04:12" and "never routed to this subscriber" are different facts."""
    _, _, version = amendment
    route_version(session, version.id)
    alert = session.scalar(select(Alert).where(Alert.document_version_id == version.id))

    deliver_alert(session, alert.id, channels={AlertChannel.IN_APP: InAppChannel()})

    attempt = session.scalar(select(AlertDelivery).where(AlertDelivery.alert_id == alert.id))
    assert attempt.status is DeliveryStatus.SENT
    assert attempt.delivered_at is not None


# --- baseline ingestion is not an amendment ------------------------------------------------------


def test_a_first_ingestion_raises_no_alert(session, cells) -> None:
    """The first version of a document is not an amendment (ADR-0003), so it emits no events and
    there is nothing to route. Reporting a whole statute as thousands of additions is the failure
    the diff stage's baseline case exists to prevent, and this side must not reintroduce it."""
    document = _document(
        session, key="baseline", title="테스트 신규", cell_ids=[cells["mfds_cosmetic"]]
    )
    version = _version(session, document, label="first")
    _subscribe(session, cell_id=cells["mfds_cosmetic"])
    session.commit()

    result = route_version(session, version.id)

    assert result.events_seen == 0
    assert result.alerts_created == 0


# --- the async half of the seam -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_coverage_denominator_reads_on_the_async_engine_too(amendment) -> None:
    """The API and the worker run on different drivers, and only one of them infers types.

    Found by running the real endpoint: ``:since IS NULL`` prepared server-side by asyncpg fails
    with *could not determine data type of parameter $1*, while the sync driver the worker uses
    accepts it without complaint. So the async wrappers need exercising on the async engine — a
    cross-seam read that only ever runs from FastAPI is not covered by a worker-side suite.
    """
    from app.store import change_event_totals_async
    from regops_shared.db import get_sessionmaker

    async with get_sessionmaker()() as db:
        unbounded = await change_event_totals_async(db)
        bounded = await change_event_totals_async(db, since=utcnow() - timedelta(days=1))

    assert sum(unbounded.values()) >= 3
    assert sum(bounded.values()) >= 3
