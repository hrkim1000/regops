"""Tier D — the recognition record, and nowhere to put the standard itself.

ISO/IEC standards and pharmacopoeias prohibit source-text storage and AI training. Enforcing that
as a flag on ``Document`` would mean the archive *can* hold standard text and only policy prevents
it. ``StandardReference`` is a separate entity with **no ``DocumentVersion`` and no column body text
could occupy** (ADR-0002 decision 2) — the rule is structural, and the CI string scan is the
backstop rather than the mechanism.

Concretely: every column here is either typed (date, enum, uuid) or a bounded ``varchar`` no longer
than ``MAX_METADATA_LENGTH``. There is no ``text`` column on this table, and
``tests/unit/test_tier_d.py`` fails if one is ever added.

This holds even where a regulation makes the standard legally binding — QMSR incorporates
ISO 13485:2016 by reference: cite the requirement, link the standard, store neither.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Final

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column

from regops_shared.constants import StandardStatus
from regops_shared.models.base import Base, TimestampMixin, UUIDPrimaryKey

#: No column on this table may exceed this, and none may be unbounded. A standard's body text
#: cannot fit in 512 characters, so there is physically nowhere for it to go.
MAX_METADATA_LENGTH: Final[int] = 512

standard_status_enum = SAEnum(
    StandardStatus,
    name="standard_status",
    values_callable=lambda e: [m.value for m in e],
    native_enum=True,
)


class StandardReference(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "standard_references"
    __table_args__ = (
        UniqueConstraint(
            "number", "edition", "recognition_number", name="uq_standard_references_identity"
        ),
    )

    #: "IEC 62304", "ISO 13485" — the identifier, which is exactly what we are allowed to keep.
    number: Mapped[str] = mapped_column(String(64), nullable=False)
    edition: Mapped[str | None] = mapped_column(String(32), nullable=True)
    issuing_body: Mapped[str | None] = mapped_column(String(64), nullable=True)

    #: Recognition / OJ citation number from the authority's own list.
    recognition_number: Mapped[str | None] = mapped_column(String(64), nullable=True)

    title: Mapped[str | None] = mapped_column(String(MAX_METADATA_LENGTH), nullable=True)

    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    withdrawal_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[StandardStatus] = mapped_column(
        standard_status_enum, nullable=False, default=StandardStatus.UNKNOWN
    )

    #: Deep link to the official copy. An IR may cite this reference; the citation resolves to this
    #: URL, never to stored text.
    official_url: Mapped[str | None] = mapped_column(String(MAX_METADATA_LENGTH), nullable=True)

    #: Which cell recognizes it, and the recognition-list source that yielded the row.
    cell_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("cells.id"), nullable=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sources.id"), nullable=True)

    #: Tier D freshness is tracked through the recognition *list*, so "still on the list as of T"
    #: is the observable — the standard itself is never fetched.
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<StandardReference {self.number} {self.edition or ''} {self.status}>"


__all__ = ["MAX_METADATA_LENGTH", "StandardReference", "standard_status_enum"]
