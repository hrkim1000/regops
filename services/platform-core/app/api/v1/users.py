"""User management. Writes are `admin` only."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from regops_shared import audit
from regops_shared.api import Meta, ok
from regops_shared.auth import Principal, get_current_principal, hash_password, require_roles
from regops_shared.constants import Role
from regops_shared.db import AsyncSession, get_db
from regops_shared.models import User

router = APIRouter(prefix="/users", tags=["users"])

SERVICE_NAME = "platform-core"


class CreateUserRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str | None = None
    role: Role = Role.VIEWER


def _serialize(user: User) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role.value,
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat(),
    }


@router.get("")
async def list_users(
    page: int = 1,
    page_size: int = 50,
    _: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> dict:
    total = await db.scalar(select(func.count()).select_from(User)) or 0
    rows = await db.scalars(
        select(User).order_by(User.created_at).offset((page - 1) * page_size).limit(page_size)
    )
    return ok(
        [_serialize(u) for u in rows],
        meta=Meta(page=page, page_size=page_size, total=total),
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_user(
    body: CreateUserRequest,
    principal: Principal = Depends(require_roles([Role.ADMIN])),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        role=body.role,
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        ) from exc

    await audit.record(
        db,
        service=SERVICE_NAME,
        action="user.create",
        actor_id=principal.id,
        entity_type="user",
        entity_id=user.id,
        payload={"email": user.email, "role": user.role.value},
    )
    await db.commit()
    return ok(_serialize(user), message="User created")


@router.get("/{user_id}")
async def get_user(
    user_id: uuid.UUID,
    _: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return ok(_serialize(user))
