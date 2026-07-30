"""The cell — the unit of scope, connector, parser profile, and coverage measurement.

Exactly 8 rows. That is enforced structurally rather than by convention: ``authority`` and
``domain`` are PostgreSQL enums with 4 and 2 values, and ``UNIQUE(authority, domain)`` admits each
pair once. A 9th row is not a policy violation to be caught in review — it cannot be inserted.
"""

from __future__ import annotations

from sqlalchemy import Enum as SAEnum
from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from regops_shared.constants import Authority, Domain
from regops_shared.models.base import Base, TimestampMixin, UUIDPrimaryKey

authority_enum = SAEnum(
    Authority, name="authority", values_callable=lambda e: [m.value for m in e], native_enum=True
)
domain_enum = SAEnum(
    Domain, name="domain", values_callable=lambda e: [m.value for m in e], native_enum=True
)


class Cell(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "cells"
    __table_args__ = (UniqueConstraint("authority", "domain", name="uq_cells_authority_domain"),)

    authority: Mapped[Authority] = mapped_column(authority_enum, nullable=False)
    domain: Mapped[Domain] = mapped_column(domain_enum, nullable=False)

    #: Denormalized `{authority}_{domain}` key — the spelling used everywhere in docs and logs.
    slug: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Cell {self.slug}>"

    @staticmethod
    def make_slug(authority: Authority, domain: Domain) -> str:
        return f"{authority.value}_{domain.value}"
