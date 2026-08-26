"""Documents, their immutable versions, and the M:N claim by cell.

Three things here are load-bearing for the citation contract:

- **Document↔Cell is M:N** (ADR-0002 decision 1). A statute claimed by two cells is ingested once;
  change events fan out to every claiming cell.
- **A version is immutable** (ADR-0002 decision 4). ``Citation`` pins to a ``DocumentVersion``, so a
  stored answer's evidence cannot silently change when the regulation is amended.
- **An annex is a child Document, not a row on a version** (ADR-0012). Annexes carry their own
  effective dates and must version independently of the parent body; a row hanging off
  ``document_version_id`` cannot do that by construction.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from regops_shared.constants import AttachmentKind, DocType
from regops_shared.models.base import Base, TimestampMixin, UUIDPrimaryKey

doc_type_enum = SAEnum(
    DocType, name="doc_type", values_callable=lambda e: [m.value for m in e], native_enum=True
)
attachment_kind_enum = SAEnum(
    AttachmentKind,
    name="attachment_kind",
    values_callable=lambda e: [m.value for m in e],
    native_enum=True,
)


class Document(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("canonical_key", name="uq_documents_canonical_key"),
        Index("ix_documents_parent_document_id", "parent_document_id"),
    )

    #: What makes 화장품법 the same Document across a title change (ADR-0002 open question 3).
    #: Phase 1 needs only the MFDS answer: 법령ID for 법령, 행정규칙일련번호 for 고시. An annex
    #: derives its key from its parent's — see ``annex_canonical_key``.
    canonical_key: Mapped[str] = mapped_column(String(255), nullable=False)

    title: Mapped[str] = mapped_column(Text, nullable=False)
    doc_type: Mapped[DocType] = mapped_column(doc_type_enum, nullable=False)
    issuing_authority: Mapped[str | None] = mapped_column(String(128), nullable=True)

    #: Set only on annexes. The parent is the body 고시/법령 the 별표 belongs to.
    parent_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id"), nullable=True
    )
    #: 별표번호 — the authority's own annex number, e.g. "2".
    annex_no: Mapped[str | None] = mapped_column(String(32), nullable=True)

    #: The source that first yielded this document. Discovery provenance, not ownership: the same
    #: document may later be re-fetched through a different source.
    source_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sources.id"), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Document {self.canonical_key} {self.doc_type}>"

    @staticmethod
    def annex_canonical_key(parent_key: str, kind: str, annex_no: str) -> str:
        """Annexes get a derived key so they are addressable without a second identifier scheme.

        ``kind`` is 별표구분 (별표 · 서식 · 별지 …) and is **not** decoration: the authority reuses
        별표번호 across kinds and across 가지번호, so a key built from the number alone collides and
        merges unrelated annexes (ADR-0012, amended 2026-08-05).
        """
        return f"{parent_key}#{kind}{annex_no}"


class DocumentCell(Base):
    """M:N claim. A document is ingested once and claimed by one or more cells."""

    __tablename__ = "document_cells"

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )
    cell_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cells.id"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )


class DocumentVersion(UUIDPrimaryKey, Base):
    """Immutable once written. There is no ``updated_at`` here on purpose.

    Two hashes, and conflating them is the mistake ADR-0003 decision 2 exists to prevent:

    - ``raw_object_key`` is ``sha256(raw response bytes)`` — the WORM key. This is what gets cited.
    - ``content_hash`` is ``sha256(canonicalized body)`` — what change detection keys on. Hashing
      raw bytes instead would make nav chrome and view counts read as amendments.
    """

    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint(
            "document_id", "language", "content_hash", name="uq_document_versions_content"
        ),
        Index("ix_document_versions_document_id_retrieved_at", "document_id", "retrieved_at"),
        Index("ix_document_versions_version_group_id", "version_group_id"),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"), nullable=False)

    #: Joins language variants of the same act (ADR-0002 decision 5). Not exercised in Phase 1 —
    #: both gated cells are MFDS and Korean-only — but diffs are computed within one language.
    version_group_id: Mapped[uuid.UUID] = mapped_column(nullable=False, default=uuid.uuid4)
    version_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    language: Mapped[str] = mapped_column(String(8), nullable=False, default="ko")

    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_object_key: Mapped[str] = mapped_column(String(160), nullable=False)
    raw_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # --- the three dates, none substituting for another (ADR-0003 decision 5) ----------------
    #: Our clock at fetch. Always present; bounds detection latency from above.
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: Source metadata (공포일자 / 발령일자 / RSS pubDate). **Null where the source exposes none** —
    #: latency for that source is then reported unmeasurable rather than zero.
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: Parse-derived, from 부칙. Null when the text states a condition rather than a calendar date.
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    #: The raw 부칙 phrase, retained whenever ``effective_date`` could not be resolved — "공포 후
    #: 6개월" and the like (ADR-0013). Never guessed into ``effective_date``: that column is part
    #: of the Citation tuple, and a low-confidence date there is indistinguishable from an
    #: authoritative one downstream.
    effective_date_phrase: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: Section identifiers the **authority itself** stated it removed in this issue — eCFR
    #: ``versions[].removed``, 27 of 72 rows for part 820 (ADR-0018 decision 8). Null where the
    #: source states nothing, which is every MFDS version: law.go.kr supplies 조문이동이전/이후, so
    #: a move there is stated and this fallback is not needed.
    #:
    #: It exists because FDA states *removal* and states no *move*, which drops CFR redesignation
    #: onto ADR-0002 decision 7's content-similarity fallback. Without this, a section the authority
    #: deleted is indistinguishable from one our differ merely failed to pair, and
    #: ``RENUMBER_MATCH_RATIO`` is low enough that a deletion can be reported as a renumber — losing
    #: the alert entirely. Stored as identifiers (``820.25``), matched against ``path_segments``.
    #:
    #: One named column rather than a generic ``meta`` blob, on the ADR-0019 precedent: the
    #: connector-meta gap (phase2.0a *Deviations* 10) stays open, and a decided need gets a typed
    #: home instead of widening it.
    authority_removed_paths: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)

    parser_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    fetch_observation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("fetch_observations.id"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )


class Attachment(UUIDPrimaryKey, TimestampMixin, Base):
    """A file link carried by a version — 별표서식파일링크 and 서식 downloads.

    This is the **archival copy and fallback**, not the ingestion route: 행정규칙 본문조회 returns
    ``<별표단위>`` with ``<별표내용>`` inline, so annex text arrives with the body and HWP/PDF
    extraction is off the Phase 1 critical path (ADR-0003 decision 10, as revised by the live
    test). The annex's *content* is a child Document; this row records where the authority's own
    file lives.

    ``raw_object_key`` is null unless the source opts into archiving the binary — fetching every
    government attachment on every poll is a politeness cost with no Phase 1 payoff.
    """

    __tablename__ = "attachments"
    __table_args__ = (
        UniqueConstraint(
            "document_version_id", "kind", "ordinal", name="uq_attachments_version_kind_ordinal"
        ),
    )

    document_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[AttachmentKind] = mapped_column(attachment_kind_enum, nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    file_format: Mapped[str | None] = mapped_column(String(16), nullable=True)

    #: A public file link published by the authority. Carries no credential — unlike a resolved
    #: API URL, which is never persisted anywhere.
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    raw_object_key: Mapped[str | None] = mapped_column(String(160), nullable=True)


__all__ = [
    "Attachment",
    "Document",
    "DocumentCell",
    "DocumentVersion",
    "attachment_kind_enum",
    "doc_type_enum",
]
