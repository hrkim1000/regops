"""Stateless JWT verification, shared by every service.

platform-core issues and signs; every service decodes locally via :func:`get_current_principal`.
There is no ``/auth/verify`` round trip — that would put a synchronous dependency on the read path
of every request.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from regops_shared.constants import ROLE_ORDER, TOKEN_TYPE_ACCESS, Role
from regops_shared.settings import get_settings

_bearer = HTTPBearer(auto_error=False)

#: bcrypt hashes at most 72 bytes and *errors* on longer input rather than truncating. Passwords
#: are normalised here so a long passphrase is accepted instead of 500-ing at the boundary.
_BCRYPT_MAX_BYTES = 72


def _normalize(plain: str) -> bytes:
    return plain.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(_normalize(plain), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_normalize(plain), hashed.encode("utf-8"))
    except ValueError:
        # Malformed stored hash — treat as a failed login, never as an exception to the caller.
        return False


@dataclass(frozen=True, slots=True)
class Principal:
    id: uuid.UUID
    email: str
    role: Role

    def has_at_least(self, required: Role) -> bool:
        return ROLE_ORDER.index(self.role) >= ROLE_ORDER.index(required)


def create_access_token(
    *, user_id: uuid.UUID, email: str, role: Role, jti: str | None = None
) -> tuple[str, str, datetime]:
    """Return ``(token, jti, expires_at)``."""
    settings = get_settings()
    token_jti = jti or uuid.uuid4().hex
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "id": str(user_id),
        "email": email,
        "role": role.value,
        "type": TOKEN_TYPE_ACCESS,
        "jti": token_jti,
        "exp": expires_at,
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, token_jti, expires_at


def decode_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc


async def get_current_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> Principal:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    payload = decode_token(credentials.credentials)
    required = ("id", "email", "role", "exp", "type")
    missing = [field for field in required if field not in payload]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token missing required claims: {', '.join(missing)}",
        )
    if payload["type"] != TOKEN_TYPE_ACCESS:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not an access token")
    try:
        role = Role(payload["role"])
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown role in token"
        ) from exc
    return Principal(id=uuid.UUID(payload["id"]), email=payload["email"], role=role)


def require_roles(allowed: list[Role]):
    """Gate a route. Reads use :func:`get_current_principal`; writes use this."""

    async def _guard(principal: Principal = Depends(get_current_principal)) -> Principal:
        if principal.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{principal.role.value}' may not perform this action",
            )
        return principal

    return _guard


__all__ = [
    "Principal",
    "create_access_token",
    "decode_token",
    "get_current_principal",
    "hash_password",
    "require_roles",
    "verify_password",
]
