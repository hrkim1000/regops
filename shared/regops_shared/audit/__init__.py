"""Audit-trail writer (ADR-0011).

A shared library function against a platform-core table — not a service call. Every service writes
through :func:`record`, which links each row into the hash chain.

Serialization is canonical (sorted keys, no whitespace, UTC isoformat) because the hash is only
meaningful if it can be recomputed identically years later by a verifier that has the rows and
nothing else.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from regops_shared.constants import AUDIT_CHAIN_GENESIS
from regops_shared.models.audit import AuditLog


def _canonical(
    *,
    actor_id: uuid.UUID | None,
    service: str,
    action: str,
    entity_type: str | None,
    entity_id: uuid.UUID | None,
    payload: dict[str, Any],
    created_at: datetime,
    prev_hash: str,
) -> str:
    return json.dumps(
        {
            "actor_id": str(actor_id) if actor_id else None,
            "service": service,
            "action": action,
            "entity_type": entity_type,
            "entity_id": str(entity_id) if entity_id else None,
            "payload": payload,
            "created_at": created_at.astimezone(UTC).isoformat(),
            "prev_hash": prev_hash,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def compute_entry_hash(**fields: Any) -> str:
    return hashlib.sha256(_canonical(**fields).encode("utf-8")).hexdigest()


async def record(
    db: AsyncSession,
    *,
    service: str,
    action: str,
    actor_id: uuid.UUID | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    payload: dict[str, Any] | None = None,
) -> AuditLog:
    """Append one entry. Flushes but does not commit — the caller commits.

    Concurrency: the chain is read-then-write, so two concurrent writers can select the same tail.
    ``entry_hash`` is UNIQUE, so the loser gets an integrity error and retries rather than forking
    the chain silently.
    """
    tail = await db.scalar(select(AuditLog).order_by(AuditLog.seq.desc()).limit(1))
    prev_hash = tail.entry_hash if tail else AUDIT_CHAIN_GENESIS

    created_at = datetime.now(UTC)
    fields = {
        "actor_id": actor_id,
        "service": service,
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "payload": payload or {},
        "created_at": created_at,
        "prev_hash": prev_hash,
    }
    entry = AuditLog(**fields, entry_hash=compute_entry_hash(**fields))
    db.add(entry)
    await db.flush()
    return entry


def verify_chain(entries: Sequence[AuditLog]) -> tuple[bool, int | None]:
    """Recompute the chain. Returns ``(ok, first_bad_seq)``.

    ``entries`` must be ordered by ``seq`` ascending and start at the beginning of the chain.
    """
    expected_prev = AUDIT_CHAIN_GENESIS
    for entry in entries:
        if entry.prev_hash != expected_prev:
            return False, entry.seq
        recomputed = compute_entry_hash(
            actor_id=entry.actor_id,
            service=entry.service,
            action=entry.action,
            entity_type=entry.entity_type,
            entity_id=entry.entity_id,
            payload=entry.payload,
            created_at=entry.created_at,
            prev_hash=entry.prev_hash,
        )
        if recomputed != entry.entry_hash:
            return False, entry.seq
        expected_prev = entry.entry_hash
    return True, None


__all__ = ["compute_entry_hash", "record", "verify_chain"]
