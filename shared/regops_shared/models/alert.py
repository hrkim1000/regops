"""The alerting surface — everything ``monitoring`` owns (ADR-0009 decision 3).

This is the pillar that carries two of the six Phase 1 gates: detection coverage ≥ 95% and
detection latency ≤ 24h, both measured end to end from the authority's publication to the owner's
alert. Four properties here are structural rather than conventional:

- **An alert is per amendment, not per clause.** The unique key is
  ``(tenant_id, cell_id, document_version_id)``, so an amendment touching 40 clauses is one alert
  carrying 40 clause references. Forty alerts would be the same information delivered as noise, and
  a subscriber who stops reading alerts fails the coverage gate as surely as a missed change.
- **Grading writes onto ``alerts``** rather than into a table of its own, until there is a reason to
  separate it (ADR-0009 decision 3). ``severity`` and the inputs behind it live on the same row.
- **All three tables are tenant-scoped from the first migration** (ADR-0005 decision 2). Tenancy
  arrives in Phase 3; backfilling a tenant column onto a delivery log is how one customer's
  regulatory alerts end up attributed to another.
- **One row per delivery *attempt*.** ``alert_deliveries`` is an append-only attempt log, not a
  mutable status field: "it failed twice and then succeeded" is the thing an operator needs to see,
  and a single row overwritten in place cannot say it.

Nothing here references a ``regulation``-owned row that this service writes. ``cell_id``,
``document_id`` and ``document_version_id`` carry database-level foreign keys because the tables sit
in one database and are modelled once; ``monitoring`` still only ever **reads** them, one-way and by
raw SQL (CLAUDE.md § The seam). ``change_event_ids`` is an array rather than a join table for the
same reason: it records which events composed this alert without claiming ownership of any of them.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from regops_shared.constants import (
    AlertChannel,
    AlertSeverity,
    AlertStatus,
    DeliveryStatus,
)
from regops_shared.models.base import Base, TimestampMixin, UUIDPrimaryKey, utcnow

alert_channel_enum = SAEnum(
    AlertChannel,
    name="alert_channel",
    values_callable=lambda e: [m.value for m in e],
    native_enum=True,
)
alert_severity_enum = SAEnum(
    AlertSeverity,
    name="alert_severity",
    values_callable=lambda e: [m.value for m in e],
    native_enum=True,
)
alert_status_enum = SAEnum(
    AlertStatus,
    name="alert_status",
    values_callable=lambda e: [m.value for m in e],
    native_enum=True,
)
delivery_status_enum = SAEnum(
    DeliveryStatus,
    name="delivery_status",
    values_callable=lambda e: [m.value for m in e],
    native_enum=True,
)


class AlertSubscription(UUIDPrimaryKey, TimestampMixin, Base):
    """Who wants to hear about changes in which cell, and where to send them.

    **Matching is on cell and only on cell** (ADR-0009 decision 5). Per ADR-0007 an IR applies to a
    cell until the Product context exists, so a product-profile column here would promise a
    precision the data cannot support — and, worse, would make shared reference data
    tenant-dependent. Product routing is phase2.2, in ``compliance``, where it is tenant-scoped by
    construction.

    ``UNIQUE NULLS NOT DISTINCT`` because ``tenant_id`` is null until Phase 3, and PostgreSQL's
    default treats two nulls as distinct — which would let the same person subscribe to the same
    cell on the same channel without limit and receive every alert N times.
    """

    __tablename__ = "alert_subscriptions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "subscriber_id",
            "cell_id",
            "channel",
            name="uq_alert_subscriptions_target",
            postgresql_nulls_not_distinct=True,
        ),
        Index("ix_alert_subscriptions_cell_id", "cell_id"),
        Index("ix_alert_subscriptions_tenant_id", "tenant_id"),
        Index("ix_alert_subscriptions_subscriber_id", "subscriber_id"),
        # A webhook with nowhere to POST is not a subscription, it is a silent hole in coverage.
        CheckConstraint(
            "channel = 'in_app' OR destination IS NOT NULL", name="destination_for_remote_channel"
        ),
    )

    tenant_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    #: The ``users`` row this belongs to. A plain UUID: ``users`` is owned by ``platform-core`` and
    #: a person reference is not a referential-integrity concern of the alerting tables.
    subscriber_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    cell_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cells.id"), nullable=False)

    channel: Mapped[AlertChannel] = mapped_column(
        alert_channel_enum, nullable=False, default=AlertChannel.IN_APP
    )
    #: Where to send it — a URL for ``WEBHOOK``, an address for ``EMAIL``, null for ``IN_APP``.
    destination: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: Floor, not filter-by-equality: a subscriber asking for ``MEDIUM`` still gets ``HIGH``.
    min_severity: Mapped[AlertSeverity] = mapped_column(
        alert_severity_enum, nullable=False, default=AlertSeverity.LOW
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<AlertSubscription {self.subscriber_id} {self.cell_id} {self.channel}>"


class Alert(UUIDPrimaryKey, Base):
    """One amendment, graded, for one cell — with every clause it touched attached.

    The four timestamps are four different facts and none substitutes for another
    (ADR-0003 decision 5, applied to the latency gate):

    - ``published_at`` — the authority's own. **Null where the source publishes none**, in which
      case latency for this alert is reported *unmeasurable*, never zero.
    - ``retrieved_at`` — our clock at fetch. Bounds detection latency from above even when the
      authority states no publication date.
    - ``detected_at`` — the earliest ``change_events.detected_at`` this alert was composed from.
    - ``created_at`` — when the alert itself existed. Composition time, and the end of the
      publication → alert measurement.

    They are copied onto the row rather than joined at read time on purpose: the latency gate is a
    claim about what was true when the alert was raised, and a re-parse can change a version's
    derived fields afterwards.
    """

    __tablename__ = "alerts"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "cell_id",
            "document_version_id",
            name="uq_alerts_target",
            postgresql_nulls_not_distinct=True,
        ),
        Index("ix_alerts_cell_id_detected_at", "cell_id", "detected_at"),
        Index("ix_alerts_status", "status"),
        Index("ix_alerts_tenant_id", "tenant_id"),
        Index("ix_alerts_owner_id", "owner_id"),
        # An alert with no clause behind it is not an alert. The renumbering-only case produces no
        # row at all rather than an empty one.
        CheckConstraint("clause_count > 0", name="clause_count_positive"),
    )

    tenant_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    cell_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cells.id"), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"), nullable=False)
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_versions.id"), nullable=False
    )
    #: The version this one amends. Null only where a diff somehow reached here without a
    #: predecessor — a baseline ingestion is not an amendment and raises no alert at all.
    from_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("document_versions.id"), nullable=True
    )

    severity: Mapped[AlertSeverity] = mapped_column(alert_severity_enum, nullable=False)
    status: Mapped[AlertStatus] = mapped_column(
        alert_status_enum, nullable=False, default=AlertStatus.PENDING
    )

    title: Mapped[str] = mapped_column(Text, nullable=False)
    #: Composed at grading time, in the subscriber-facing wording. States the cell-level limitation
    #: outright rather than implying product-level precision.
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")

    #: Substantive clauses only — renumbers and moves are excluded before this is counted.
    clause_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Which ``change_events`` composed this alert. Provenance for the coverage audit: an event that
    #: reached no alert and an event that was deliberately suppressed must be tellable apart.
    change_event_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(PGUUID(as_uuid=True)), nullable=False, default=list
    )
    #: Ordered ``[{clause_path, change_kind, from_clause_path}]``. ``jsonb`` rather than a fourth
    #: table: these are the alert's *content*, read only with the alert, and ADR-0009 gives
    #: ``monitoring`` three tables.
    clause_references: Mapped[list | dict | None] = mapped_column(JSONB, nullable=True)

    #: The grading inputs, kept beside the grade. A severity nobody can re-derive is a number that
    #: cannot be challenged when the pilot disagrees with it.
    cited_by_locked_ir: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    locked_ir_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    #: Owner assignment — recorded, attributed and audited (ADR-0011). An alert nobody owns is an
    #: alert nobody actions, and "who was told to deal with this" is exactly the question an audit
    #: asks after a missed amendment.
    owner_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Alert {self.severity} {self.clause_count} clauses {self.status}>"


class AlertDelivery(UUIDPrimaryKey, Base):
    """One attempt to reach one subscriber. Append-only.

    Written **before** the attempt is made, so a worker that dies mid-send leaves a ``PENDING`` row
    rather than no trace. ``next_retry_at`` records when the retry was scheduled for — the retry
    itself is a Celery ``countdown``, not a table poll, because ``monitoring`` runs no beat and a
    sweep would re-discover work that was already scheduled.
    """

    __tablename__ = "alert_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "alert_id", "subscription_id", "attempt", name="uq_alert_deliveries_attempt"
        ),
        Index("ix_alert_deliveries_alert_id", "alert_id"),
        Index("ix_alert_deliveries_subscription_id", "subscription_id"),
        Index("ix_alert_deliveries_status", "status"),
        CheckConstraint("attempt >= 1", name="attempt_positive"),
    )

    tenant_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    alert_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False
    )
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("alert_subscriptions.id", ondelete="CASCADE"), nullable=False
    )

    #: Copied from the subscription at send time. A subscriber who repoints their webhook must not
    #: rewrite where a past attempt actually went.
    channel: Mapped[AlertChannel] = mapped_column(alert_channel_enum, nullable=False)
    destination: Mapped[str | None] = mapped_column(Text, nullable=True)

    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[DeliveryStatus] = mapped_column(
        delivery_status_enum, nullable=False, default=DeliveryStatus.PENDING
    )
    #: Why it failed, truncated to something a list view can render. The full transport exception is
    #: logged; this is what an operator reads next to the row.
    error: Mapped[str | None] = mapped_column(String(512), nullable=True)

    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<AlertDelivery {self.channel} attempt={self.attempt} {self.status}>"


__all__ = [
    "Alert",
    "AlertDelivery",
    "AlertSubscription",
    "alert_channel_enum",
    "alert_severity_enum",
    "alert_status_enum",
    "delivery_status_enum",
]
