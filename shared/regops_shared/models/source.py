"""The source registry and the record of every time we looked at it.

``sources`` is the runtime projection of
[docs/import-source-map.md](../../../docs/import-source-map.md), which stays the single catalog —
this table is seeded *from* it and never becomes a second list.

Two invariants are structural here rather than procedural:

1. **No credential is storable.** ``url_template`` holds a placeholder; the resolved URL is built at
   request time and is never persisted. ``fetch_observations`` has no column for a request URL, so a
   connector cannot leak a key into the append-only trail even by accident (ADR-0003 decision 13).
2. **A non-ingestible source has no fetch path.** ``ingestible`` gates the scheduler *and* the
   connector API; Tier D rows are seeded with it false (ADR-0003 decision 7).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from regops_shared.constants import (
    Authority,
    DriftSignal,
    FetchOutcome,
    SourceBlock,
    SourceTier,
)
from regops_shared.models.base import Base, TimestampMixin, UUIDPrimaryKey
from regops_shared.models.cell import authority_enum


def _pg_enum(enum_cls: type, name: str) -> SAEnum:
    return SAEnum(
        enum_cls, name=name, values_callable=lambda e: [m.value for m in e], native_enum=True
    )


source_block_enum = _pg_enum(SourceBlock, "source_block")
source_tier_enum = _pg_enum(SourceTier, "source_tier")
fetch_outcome_enum = _pg_enum(FetchOutcome, "fetch_outcome")
drift_signal_enum = _pg_enum(DriftSignal, "drift_signal")


class Source(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "sources"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_sources_slug"),
        Index("ix_sources_cell_id_block", "cell_id", "block"),
    )

    #: Stable seed key — ``{cell_slug}.{block}.{name}``. Re-seeding upserts on this, so the
    #: catalog can be re-applied without duplicating rows.
    slug: Mapped[str] = mapped_column(String(160), nullable=False)

    cell_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cells.id"), nullable=False)
    block: Mapped[SourceBlock] = mapped_column(source_block_enum, nullable=False)

    #: Position within the block — the catalog's own ordering, which is ingestion priority.
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    title: Mapped[str] = mapped_column(Text, nullable=False)

    #: URL **template**. Credential parameters appear as ``{OC}``-style placeholders only.
    url_template: Mapped[str | None] = mapped_column(Text, nullable=True)

    tier: Mapped[SourceTier] = mapped_column(source_tier_enum, nullable=False)

    #: False for Tier D and for login-gated portals. The scheduler skips it and the connector API
    #: rejects it — there is no code path from a non-ingestible source to stored body text.
    ingestible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    #: Registry key of the connector that fetches this source. Null for reference-only rows.
    connector: Mapped[str | None] = mapped_column(String(64), nullable=True)

    #: Non-secret connector arguments — 법령ID, 행정규칙일련번호, RSS category. Never a credential.
    params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    #: Interval is derived from block + tier. An override is allowed, but the reason lives here
    #: (phase 1.0 § Source registry) and both columns are set together.
    interval_override_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    interval_override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: HTTP cache validators from the last fetch — a 304 is the cheapest fetch_observation there is.
    http_etag: Mapped[str | None] = mapped_column(String(255), nullable=True)
    http_last_modified: Mapped[str | None] = mapped_column(String(64), nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Source {self.slug} tier={self.tier} ingestible={self.ingestible}>"


class SourceSchedule(TimestampMixin, Base):
    """What the beat reads. One row per source; ``interval_seconds`` is the *derived* value."""

    __tablename__ = "source_schedules"

    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True
    )
    interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    next_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: Set false by an operator when a source is drifting or the authority has asked us to stop.
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class FetchObservation(UUIDPrimaryKey, Base):
    """Written on **every** attempt, changed or not (ADR-0003 decision 3).

    This is not logging. Detection coverage is measured by asking "did the system see amendment X?",
    which is only answerable if "we checked source S at time T and it was unchanged" is a stored
    fact — and it distinguishes *we missed it* from *we never looked*.

    There is deliberately **no resolved-URL column**: the append-only trail outlives any key
    rotation, so a credential written here could never be cleaned up.
    """

    __tablename__ = "fetch_observations"
    __table_args__ = (
        Index("ix_fetch_observations_source_id_fetched_at", "source_id", "fetched_at"),
    )

    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id"), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)

    #: sha256 of the **canonicalized** body, not of the response bytes. Null on transport failure.
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    connector_version: Mapped[str] = mapped_column(String(32), nullable=False)
    outcome: Mapped[FetchOutcome] = mapped_column(fetch_outcome_enum, nullable=False)

    #: From source metadata (공고일 / RSS pubDate). Stays **null** where the source exposes none —
    #: never defaulted to ``fetched_at``, which would make the latency gate pass by construction.
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    artifact_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )


class StructureDriftAlert(UUIDPrimaryKey, TimestampMixin, Base):
    """A site redesign is an operator alert, never a ChangeEvent (ADR-0003 decision 6).

    Emitting drift as regulatory change would generate thousands of false alerts and destroy trust
    in the monitoring pillar. Resolution is one of the two RBAC-restricted actions — a human
    assertion enters the audit trail.
    """

    __tablename__ = "structure_drift_alerts"
    __table_args__ = (
        Index("ix_structure_drift_alerts_source_id_resolved_at", "source_id", "resolved_at"),
    )

    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id"), nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    signal: Mapped[DriftSignal] = mapped_column(drift_signal_enum, nullable=False)
    expected: Mapped[str | None] = mapped_column(Text, nullable=True)
    actual: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class SourceDiscoveryRun(UUIDPrimaryKey, Base):
    """Reconciles the curated catalog against the authority's own list (ADR-0003 decision 11).

    A hand-maintained list silently caps detection coverage at whatever someone remembered to add.
    This converts that from an unknown into a measurable delta.
    """

    __tablename__ = "source_discovery_runs"

    authority: Mapped[Authority] = mapped_column(authority_enum, nullable=False)
    ran_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    upstream_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    matched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unmatched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: The unmatched entries themselves, so the delta is actionable rather than just a count.
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )


__all__ = [
    "FetchObservation",
    "Source",
    "SourceDiscoveryRun",
    "SourceSchedule",
    "StructureDriftAlert",
    "drift_signal_enum",
    "fetch_outcome_enum",
    "source_block_enum",
    "source_tier_enum",
]
