"""Who hears about changes in which cell.

**Cell is the only routing dimension in Phase 1**, and that is a decision rather than a shortcut.
Per ADR-0007 an IR applies to a cell until the Product context exists, so a product field here would
promise a precision the data cannot support — and putting product-profile routing in `monitoring`
would make shared reference data tenant-dependent, which is the exact coupling ADR-0009 decision 5
keeps out. Product routing arrives with `compliance` in phase2.2, tenant-scoped by construction.

Subscribing is an *ordinary* action, not a restricted one: the two restricted actions in Phase 1
are locking an IR and resolving a structure-drift alert (CLAUDE.md § Security), because those are
where a human assertion enters the audit trail. Anyone authenticated may subscribe themselves;
only an ``admin`` may subscribe somebody else, since that is a claim about another person's inbox.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from regops_shared.api import Meta, ok
from regops_shared.auth import Principal, get_current_principal
from regops_shared.constants import AlertChannel, AlertSeverity, Role
from regops_shared.db import AsyncSession, get_db

from ...models import AlertSubscription
from ...store import cell_by_slug_async

router = APIRouter(prefix="/api/v1", tags=["monitoring"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[Principal, Depends(get_current_principal)]

SUBSCRIPTION_PAGE_SIZE = 100
SUBSCRIPTION_PAGE_SIZE_MAX = 500


class SubscriptionRequest(BaseModel):
    """``cell`` is the slug — ``mfds_cosmetic`` — because that is the spelling used everywhere.

    Naming the cell by id would make every caller resolve it first, and the slug is the identifier
    the source map, the logs and the UI already share.
    """

    cell: str = Field(description="Cell slug, e.g. mfds_samd")
    channel: AlertChannel = Field(default=AlertChannel.IN_APP)
    destination: str | None = Field(
        default=None, description="Webhook URL or address; omit for in_app"
    )
    min_severity: AlertSeverity = Field(
        default=AlertSeverity.LOW,
        description="Floor, not equality — asking for medium still delivers high",
    )
    subscriber_id: uuid.UUID | None = Field(
        default=None, description="Admin only; defaults to the caller"
    )


class SubscriptionUpdate(BaseModel):
    destination: str | None = None
    min_severity: AlertSeverity | None = None
    enabled: bool | None = None


@router.post("/subscriptions", status_code=status.HTTP_201_CREATED)
async def create_subscription(
    body: SubscriptionRequest, db: DbSession, principal: CurrentUser
) -> dict[str, Any]:
    """Subscribe to a cell. Re-subscribing to the same cell and channel updates in place.

    Idempotent on ``(tenant, subscriber, cell, channel)`` rather than 409-ing: the natural client
    behaviour is "make sure I am subscribed", and a duplicate-key error would push every caller into
    writing the same read-then-write it can get here for free.
    """
    subscriber_id = body.subscriber_id or principal.id
    if subscriber_id != principal.id and principal.role is not Role.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only an admin may subscribe another user")

    cell = await cell_by_slug_async(db, body.cell)
    if cell is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown cell '{body.cell}'")
    if body.channel is not AlertChannel.IN_APP and not body.destination:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Channel '{body.channel.value}' requires a destination",
        )

    existing = await db.scalar(
        select(AlertSubscription).where(
            AlertSubscription.subscriber_id == subscriber_id,
            AlertSubscription.cell_id == cell.cell_id,
            AlertSubscription.channel == body.channel,
            AlertSubscription.tenant_id.is_(None),
        )
    )
    if existing is None:
        existing = AlertSubscription(
            subscriber_id=subscriber_id,
            cell_id=cell.cell_id,
            channel=body.channel,
        )
        db.add(existing)
    existing.destination = body.destination
    existing.min_severity = body.min_severity
    existing.enabled = True

    await db.commit()
    return {
        "code": status.HTTP_201_CREATED,
        "status": "success",
        "message": "Subscribed",
        "data": _subscription_out(existing, cell_slug=cell.slug),
        "meta": None,
    }


@router.get("/subscriptions")
async def list_subscriptions(
    db: DbSession,
    principal: CurrentUser,
    subscriber_id: Annotated[
        uuid.UUID | None, Query(description="Admin only; defaults to the caller")
    ] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(SUBSCRIPTION_PAGE_SIZE, ge=1, le=SUBSCRIPTION_PAGE_SIZE_MAX),
) -> dict[str, Any]:
    """A subscriber's own subscriptions. An admin may read another's."""
    target = subscriber_id or principal.id
    if target != principal.id and principal.role is not Role.ADMIN:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only an admin may read another user's subscriptions"
        )

    stmt = select(AlertSubscription).where(AlertSubscription.subscriber_id == target)
    total = (
        await db.scalar(
            select(func.count())
            .select_from(AlertSubscription)
            .where(AlertSubscription.subscriber_id == target)
        )
        or 0
    )
    rows = list(
        await db.scalars(
            stmt.order_by(AlertSubscription.created_at)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    slugs = await _slugs(db, [row.cell_id for row in rows])
    return ok(
        [_subscription_out(row, cell_slug=slugs.get(row.cell_id, "")) for row in rows],
        meta=Meta(page=page, page_size=page_size, total=total),
    )


@router.patch("/subscriptions/{subscription_id}")
async def update_subscription(
    subscription_id: uuid.UUID,
    body: SubscriptionUpdate,
    db: DbSession,
    principal: CurrentUser,
) -> dict[str, Any]:
    """Change a destination, raise the floor, or switch it off.

    Disabling rather than deleting is the default a client should reach for: a deleted subscription
    takes its delivery history with it (``ON DELETE CASCADE``), and "we did tell them, three times"
    is exactly the record an audit after a missed amendment asks for.
    """
    subscription = await db.get(AlertSubscription, subscription_id)
    if subscription is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Subscription not found")
    if subscription.subscriber_id != principal.id and principal.role is not Role.ADMIN:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only an admin may change another user's subscription"
        )

    if body.destination is not None:
        subscription.destination = body.destination
    if body.min_severity is not None:
        subscription.min_severity = body.min_severity
    if body.enabled is not None:
        subscription.enabled = body.enabled

    if subscription.channel is not AlertChannel.IN_APP and not subscription.destination:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Channel '{subscription.channel.value}' requires a destination",
        )

    await db.commit()
    slugs = await _slugs(db, [subscription.cell_id])
    return ok(_subscription_out(subscription, cell_slug=slugs.get(subscription.cell_id, "")))


# --- shaping ---------------------------------------------------------------------------------


async def _slugs(db: AsyncSession, cell_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    from ...store import cells_by_id_async

    return {cell_id: cell.slug for cell_id, cell in (await cells_by_id_async(db, cell_ids)).items()}


def _subscription_out(subscription: AlertSubscription, *, cell_slug: str) -> dict[str, Any]:
    return {
        "id": str(subscription.id),
        "subscriber_id": str(subscription.subscriber_id),
        "cell_id": str(subscription.cell_id),
        "cell": cell_slug,
        "channel": subscription.channel.value,
        "destination": subscription.destination,
        "min_severity": subscription.min_severity.value,
        "enabled": subscription.enabled,
    }


__all__ = ["router"]
