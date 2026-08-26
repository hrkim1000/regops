"""The clause store, its diffs, and the change events they emit.

This is the model ADR-0002 calls the most expensive thing in RegOps to change later: altering it
after ingestion means re-parsing the WORM archive and invalidating every stored citation. Four
properties are load-bearing:

- **``Clause`` is domain-neutral** (ADR-0002 decision 3). 조/항/호/목 and Part/Subpart/§ are both
  ordered hierarchical paths. There is no SaMD-only or Cosmetic-only column here, and adding one is
  the exact action the phase 1.1 falsifier forbids.
- **An annex table row is a ``Clause``** (ADR-0014), addressed by ``clause_path`` like any other, so
  ``ir_citations`` needs no branch for annexes and there is no second row store to keep in sync.
- **``effective_date`` is paired with ``effective_date_phrase``** (ADR-0013). A date that cannot be
  resolved to a calendar day stays null and the raw 부칙 phrase is kept; a computed date is never
  written into the column that forms part of the Citation tuple.
- **Renumbering is a change kind, not a delete plus an add** (ADR-0002 decision 7). For
  ``law.go.kr`` the authority states the move itself in 조문이동이전/조문이동이후, which is why
  those land on the clause rather than being inferred later.

Clauses are immutable *as a parse result*: nothing updates a clause's text in place. Re-parsing a
version deletes its clauses and writes them again (ADR-0015), which is a replacement of a derived
artefact, not a mutation of evidence — the evidence is the archived bytes, and they never change.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
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
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from regops_shared.constants import ChangeKind, ClauseKind
from regops_shared.models.base import Base, UUIDPrimaryKey, utcnow

clause_kind_enum = SAEnum(
    ClauseKind, name="clause_kind", values_callable=lambda e: [m.value for m in e], native_enum=True
)
change_kind_enum = SAEnum(
    ChangeKind, name="change_kind", values_callable=lambda e: [m.value for m in e], native_enum=True
)


class Clause(UUIDPrimaryKey, Base):
    """One addressable unit of a document version.

    ``clause_path`` is the rendered address (``제2장/제8조/제1항/제3호``, ``별표2/표1/행3``) and
    ``path_segments`` is the ordered array backing it, indexed for prefix queries and tree
    operations. They are two views of one value and are always written together.
    """

    __tablename__ = "clauses"
    __table_args__ = (
        UniqueConstraint("document_version_id", "clause_path", name="uq_clauses_version_path"),
        Index("ix_clauses_document_version_id_ordinal", "document_version_id", "ordinal"),
        Index("ix_clauses_path_segments", "path_segments", postgresql_using="gin"),
        Index("ix_clauses_clause_path", "clause_path"),
        Index("ix_clauses_content_hash", "content_hash"),
    )

    document_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False
    )

    clause_path: Mapped[str] = mapped_column(String(512), nullable=False)
    path_segments: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    #: Position among **all** clauses of the version, in document order — a reading order, not an
    #: identity. Inserting one article shifts every ordinal below it, so the diff stage must never
    #: treat a changed ordinal as a change to the clause: the *path* is the position.
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    kind: Mapped[ClauseKind] = mapped_column(
        clause_kind_enum, nullable=False, default=ClauseKind.PROSE
    )
    heading: Mapped[str | None] = mapped_column(Text, nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")

    #: Per-table column map (ADR-0014 decision 4). On a ``TABLE`` clause, the ordered header labels;
    #: on a ``TABLE_ROW``, ``{header_label: cell_text}``. ``jsonb`` not columns because every
    #: table has a different column set — 별표 2 has five, 별표 1 has three — so a fixed schema is
    #: impossible and exact-match lookup has to name the column at query time.
    row_columns: Mapped[dict | list | None] = mapped_column(JSONB, nullable=True)

    #: Set only where the clause states an application date distinct from its version's
    #: (ADR-0003 decision 5). Null throughout the gated corpus today: 조문시행일자 is constant per
    #: document there, measured across all nine 법령 (ADR-0016).
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_date_phrase: Mapped[str | None] = mapped_column(Text, nullable=True)

    parent_clause_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("clauses.id", ondelete="CASCADE"), nullable=True
    )

    #: The authority's own identifier for this unit — 조문키 for 법령, absent elsewhere. The primary
    #: renumber signal, because a move it states beats a similarity we infer.
    source_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: 조문이동이전 / 조문이동이후. Populated only where the source publishes them.
    moved_from_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    moved_to_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: 조문변경여부 — the authority's own "this article changed" flag, used to cross-check our diff
    #: against theirs (ADR-0003 decision 12).
    authority_changed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    #: ``sha256`` of the normalized clause text. The diff stage compares hashes before it compares
    #: text, so an unchanged clause costs one equality test rather than a similarity computation.
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Clause {self.clause_path} {self.kind}>"


class ClauseDiff(UUIDPrimaryKey, Base):
    """What changed between two versions of one document, per clause path.

    ``from_version_id`` is null for the first version of a document: there is a real difference
    between "this clause is new in an amendment" and "this document was ingested for the first
    time", and collapsing them would report an entire statute as thousands of additions.
    """

    __tablename__ = "clause_diffs"
    __table_args__ = (
        UniqueConstraint(
            "to_version_id", "clause_path", "change_kind", name="uq_clause_diffs_target"
        ),
        Index("ix_clause_diffs_to_version_id", "to_version_id"),
        Index("ix_clause_diffs_from_version_id", "from_version_id"),
        Index("ix_clause_diffs_needs_review", "needs_review"),
    )

    from_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("document_versions.id"), nullable=True
    )
    to_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_versions.id"), nullable=False
    )

    #: The path in the **new** version, or in the old one for a removal — the address a reader would
    #: look up. ``from_clause_path`` carries the other side of a renumber.
    clause_path: Mapped[str] = mapped_column(String(512), nullable=False)
    from_clause_path: Mapped[str | None] = mapped_column(String(512), nullable=True)

    change_kind: Mapped[ChangeKind] = mapped_column(change_kind_enum, nullable=False)

    from_clause_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("clauses.id", ondelete="SET NULL"), nullable=True
    )
    to_clause_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("clauses.id", ondelete="SET NULL"), nullable=True
    )

    #: Content similarity in ``[0, 1]`` for the pair. Null where the match came from the authority's
    #: own 조문이동 fields, because then nothing was inferred.
    similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    #: How the pairing was established — ``path``, ``authority``, ``content_hash``, ``similarity``,
    #: or ``similarity_contested``. Kept because they carry very different confidence and the
    #: detection-coverage audit needs to tell them apart.
    #:
    #: ``similarity_contested`` is the last of these and the least comfortable: content similarity
    #: paired two clauses the authority had *stated* it removed (eCFR ``versions[].removed``,
    #: ADR-0018 decision 8). Such a pairing must clear ``RENUMBER_CONFIDENT_RATIO`` rather than
    #: ``RENUMBER_MATCH_RATIO`` and is always ``needs_review``, because we are contradicting the
    #: authority about what happened to a provision.
    match_basis: Mapped[str | None] = mapped_column(String(32), nullable=True)

    #: A low-confidence renumber match is written *and* queued: dropping it would lose the change,
    #: and accepting it silently would assert an identity nobody checked.
    needs_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<ClauseDiff {self.change_kind} {self.clause_path}>"


class ChangeEvent(UUIDPrimaryKey, Base):
    """One ``ClauseDiff``, routed to one claiming cell (ADR-0003 decision 8).

    Fan-out is per cell, so an amendment to a document claimed by both gated cells produces two
    events and a single-cell document produces one. ``monitoring`` reads this table one-way by raw
    SQL and never imports this model.

    Severity is **ungraded in Phase 1** — the column exists so grading is additive later. ADR-0003
    decision 8 defers it deliberately: Phase 1 measures whether events are complete and timely, and
    grading quality needs a corpus to calibrate against.
    """

    __tablename__ = "change_events"
    __table_args__ = (
        UniqueConstraint("clause_diff_id", "cell_id", name="uq_change_events_diff_cell"),
        Index("ix_change_events_cell_id_detected_at", "cell_id", "detected_at"),
        Index("ix_change_events_document_id", "document_id"),
    )

    clause_diff_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clause_diffs.id", ondelete="CASCADE"), nullable=False
    )
    cell_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cells.id"), nullable=False)
    #: Denormalized from the diff's version so `monitoring` can filter by document without joining
    #: back through two tables across the service seam.
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"), nullable=False)

    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    severity: Mapped[str | None] = mapped_column(String(16), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


__all__ = [
    "ChangeEvent",
    "Clause",
    "ClauseDiff",
    "change_kind_enum",
    "clause_kind_enum",
]
