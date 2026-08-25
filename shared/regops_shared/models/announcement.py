"""An amendment that has been announced, whether or not its text exists yet.

[ADR-0019](../../../docs/design/ADR-0019-announced-amendments.md). A Federal Register final rule is
provenance, not a ``Document`` — its body is not what an RA cites (ADR-0018 decision 4). But
"provenance on the version" cannot hold the rows that matter most: the eCFR 404s on any future date,
so a rule published and not yet in force has **no version to be provenance of**, and FDA carries
rules today effective as far out as 2033.

So this is the ``StandardReference`` shape — a different entity earns a table
(ADR-0002 decision 2) — upserted from connector records with ``source_id`` and ``last_seen_at``.

**Authority-neutral on purpose, FDA-only in practice.** Naming it after the Federal Register would
bake one authority into the schema, and the concept is not FDA's: an amendment announced before its
text is readable is 공포-before-시행, an Official Journal publication, an FDA final rule. MFDS needs
no row here because ``target=eflaw`` serves the pending 본문, so ADR-0016 decision 1 makes those
*versions* — the authorities differ in whether the text exists yet, not in whether an amendment was
announced.

**Never a source of regulation text.** These rows are evidence *about* the corpus, not evidence
*in* it. Nothing cites an announcement, and nothing downstream may read one as a provision.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from regops_shared.models.base import Base, TimestampMixin, UUIDPrimaryKey


class AmendmentAnnouncement(UUIDPrimaryKey, TimestampMixin, Base):
    """One announcing document — a Federal Register final rule, and later its equivalents."""

    __tablename__ = "amendment_announcements"
    __table_args__ = (
        # Keyed with the authority so the uniqueness claim is one an authority can actually make
        # about its own numbering, and a second authority's refs cannot collide with the first's.
        UniqueConstraint("authority", "ref", name="uq_amendment_announcements_identity"),
    )

    #: ``fda``. Matches ``cells.authority`` values, but is not an FK: an announcement is about an
    #: authority, not about one of its cells, and the QMSR rule reaches both FDA cells at once.
    authority: Mapped[str] = mapped_column(String(16), nullable=False)

    #: The authority's own identifier — ``2024-01709``, the Federal Register document number.
    ref: Mapped[str] = mapped_column(String(64), nullable=False)

    #: How the authority cites it in prose: ``89 FR 7496``. Kept because it is what appears in the
    #: eCFR's own ``<SOURCE>``/``<CITA>`` notes — though **not** as a join key, since the eCFR
    #: sources Part 820 to ``89 FR 7523``, a page *inside* this rule (ADR-0018 decision 4).
    citation: Mapped[str | None] = mapped_column(String(64), nullable=True)

    title: Mapped[str | None] = mapped_column(String(512), nullable=True)

    published_on: Mapped[date | None] = mapped_column(Date, nullable=True)

    #: The **legally stated** effective date, and nullable on purpose: 6 of Part 820's 16 rules
    #: state none. ADR-0013 — null with the phrase retained, never a date we inferred. This is the
    #: column a later step reads *in preference to* the eCFR's own ``amendment_date``, which makes a
    #: guess here worse than a guess anywhere else.
    effective_on: Mapped[date | None] = mapped_column(Date, nullable=True)

    #: The authority's ``dates`` prose, verbatim — "This rule is effective February 2, 2026. The
    #: incorporation by reference…". Retained whether or not the date resolved, because it is the
    #: input a later resolver would need and the only evidence left when it did not.
    effective_date_phrase: Mapped[str | None] = mapped_column(Text, nullable=True)

    official_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    #: The feed row that yielded this, and when it was last still in that feed.
    source_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sources.id"), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<AmendmentAnnouncement {self.authority}:{self.ref} effective={self.effective_on}>"


class AnnouncementDocument(Base):
    """Which Documents an announcement amends. M:N, because one rule amends several Parts.

    The QMSR rule names Parts **4 and 820**. One row per (rule, Part) on the announcement itself
    would repeat ``effective_on`` per Part and let the copies drift — the same reason
    ``document_cells`` exists rather than a ``cell`` column on ``documents``.

    A rule naming a Part outside the corpus simply has no row for it. The announcement still exists,
    which is the point; coverage is a question about Parts, not about rules.
    """

    __tablename__ = "announcement_documents"

    announcement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("amendment_announcements.id", ondelete="CASCADE"), primary_key=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )


__all__ = ["AmendmentAnnouncement", "AnnouncementDocument"]
