"""Append-only audit trail with a hash chain (ADR-0011).

The table lives in platform-core and is written through :mod:`regops_shared.audit`, never by
calling an audit *service* — that would make the audit trail a synchronous dependency on the write
path of everything (ADR-0005 decision 4).

Immutability is enforced at two levels:

* the application role holds no ``UPDATE`` or ``DELETE`` grant on this table (migration ``0001``);
* each row's ``entry_hash`` covers the previous row's hash, so an edit made by a superuser — the
  one actor grants cannot stop — breaks the chain and is *detectable*.

Tamper-resistance alone is not tamper-evidence, and 21 CFR Part 11 expects the latter.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from regops_shared.models.base import Base, utcnow


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_entity", "entity_type", "entity_id"),
        Index("ix_audit_log_actor_id_created_at", "actor_id", "created_at"),
    )

    #: Monotonic sequence — the chain order. Not a UUID, because the chain needs a total order
    #: that does not depend on clock skew between services.
    seq: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    service: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(64))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    #: Previous row's ``entry_hash``; ``AUDIT_CHAIN_GENESIS`` for the first row.
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    #: sha256 over the canonical serialization of this row plus ``prev_hash``.
    entry_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<AuditLog {self.seq} {self.service}.{self.action}>"
