"""Auth endpoints. platform-core issues and signs; other services only decode."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select

from regops_shared import audit
from regops_shared.api import ok
from regops_shared.auth import (
    Principal,
    create_access_token,
    get_current_principal,
    verify_password,
)
from regops_shared.db import AsyncSession, get_db
from regops_shared.models import Session, User

router = APIRouter(prefix="/auth", tags=["auth"])

SERVICE_NAME = "platform-core"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


@router.post("/login")
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)) -> dict:
    user = await db.scalar(select(User).where(User.email == body.email))

    # Same message and code for unknown email and wrong password — distinguishing them tells an
    # attacker which half of the guess was right.
    if user is None or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")

    token, jti, expires_at = create_access_token(user_id=user.id, email=user.email, role=user.role)
    db.add(Session(user_id=user.id, jti=jti, expires_at=expires_at))
    await audit.record(
        db,
        service=SERVICE_NAME,
        action="auth.login",
        actor_id=user.id,
        entity_type="user",
        entity_id=user.id,
        payload={"jti": jti},
    )
    await db.commit()

    return ok(
        {
            "access_token": token,
            "token_type": "bearer",
            "expires_at": expires_at.isoformat(),
            "role": user.role.value,
        },
        message="Login successful",
    )


@router.get("/me")
async def me(principal: Principal = Depends(get_current_principal)) -> dict:
    return ok({"id": str(principal.id), "email": principal.email, "role": principal.role.value})


@router.post("/logout")
async def logout(
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await audit.record(
        db,
        service=SERVICE_NAME,
        action="auth.logout",
        actor_id=principal.id,
        entity_type="user",
        entity_id=principal.id,
    )
    await db.commit()
    return ok(None, message="Logged out")
