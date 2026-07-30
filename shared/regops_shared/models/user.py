"""Identity, owned by platform-core."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String, Uuid
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from regops_shared.constants import Role
from regops_shared.models.base import Base, TimestampMixin, UUIDPrimaryKey

role_enum = SAEnum(
    Role, name="userrole", values_callable=lambda e: [m.value for m in e], native_enum=True
)


class User(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(role_enum, nullable=False, default=Role.VIEWER)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<User {self.email} {self.role.value}>"


class Session(UUIDPrimaryKey, TimestampMixin, Base):
    """Issued-token record. Verification stays stateless (services decode the JWT); this exists so
    a token can be revoked and so login activity is auditable."""

    __tablename__ = "sessions"
    __table_args__ = (Index("ix_sessions_user_id_expires_at", "user_id", "expires_at"),)

    #: Plain Uuid, no ORM ForeignKey across a service boundary.
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    jti: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
