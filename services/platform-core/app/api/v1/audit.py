"""Audit-trail read surface, including chain verification (ADR-0011).

There is no write endpoint. Services append through ``regops_shared.audit.record`` against this
service's table — calling an audit *service* would put a synchronous dependency on the write path
of everything (ADR-0005 decision 4).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from regops_shared import audit as audit_lib
from regops_shared.api import Meta, ok
from regops_shared.auth import Principal, get_current_principal, require_roles
from regops_shared.constants import Role
from regops_shared.db import AsyncSession, get_db
from regops_shared.models import AuditLog

router = APIRouter(prefix="/audit", tags=["audit"])


def _serialize(entry: AuditLog) -> dict:
    return {
        "seq": entry.seq,
        "actor_id": str(entry.actor_id) if entry.actor_id else None,
        "service": entry.service,
        "action": entry.action,
        "entity_type": entry.entity_type,
        "entity_id": str(entry.entity_id) if entry.entity_id else None,
        "payload": entry.payload,
        "created_at": entry.created_at.isoformat(),
        "prev_hash": entry.prev_hash,
        "entry_hash": entry.entry_hash,
    }


@router.get("")
async def list_entries(
    page: int = 1,
    page_size: int = 50,
    _: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> dict:
    total = await db.scalar(select(func.count()).select_from(AuditLog)) or 0
    rows = await db.scalars(
        select(AuditLog).order_by(AuditLog.seq).offset((page - 1) * page_size).limit(page_size)
    )
    return ok([_serialize(e) for e in rows], meta=Meta(page=page, page_size=page_size, total=total))


@router.post("/verify")
async def verify(
    _: Principal = Depends(require_roles([Role.ADMIN])),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Recompute the whole chain.

    Phase 0 verifies in one pass, which is fine at PoC volume. When the trail outgrows memory this
    becomes a windowed job with checkpointed anchors — noted rather than pre-built.
    """
    entries = list(await db.scalars(select(AuditLog).order_by(AuditLog.seq)))
    intact, first_bad = audit_lib.verify_chain(entries)
    return ok(
        {"intact": intact, "entries_checked": len(entries), "first_bad_seq": first_bad},
        message="Audit chain intact" if intact else "Audit chain BROKEN",
    )
