"""InfoRequirements and their citations.

**Phase 1.1 creates these tables and writes only one field on one of them.** IR extraction is
[phase1.2](../../../docs/plan/phase1.2_ir_extraction.md); what 1.1 needs is somewhere for
superseded-citation detection to land, because *"amending a cited clause flags the citation
superseded and leaves its text resolvable"* is a 1.1 acceptance criterion and an untestable
criterion is not a criterion.

So the diff stage writes ``IRCitation.superseded_at`` and ``IR.status = stale``, and everything else
here stays unwritten until 1.2. Two invariants are already structural:

- **An IR without a citation does not exist** (ADR-0004 decision 2). ``ir_citations.ir_id`` is
  ``NOT NULL`` and there is no draft state for an uncited IR. Enforcing the *minimum of one*
  citation is 1.2's job at the extraction boundary; what the schema guarantees is that a citation
  cannot float free of an IR.
- **A citation names an immutable version, never "current"** (ADR-0002 decision 4). The tuple is
  ``(document_id, document_version_id, clause_path, effective_date)`` and it is never rewritten —
  an amendment sets ``superseded_at`` and leaves the original resolvable.

``extraction_run_id`` and ``clause_classifications`` (ADR-0004's schema) are deliberately absent:
they belong to the extraction pipeline 1.2 builds, and a dangling column with no table behind it is
worse than an additive migration.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column

from regops_shared.constants import Domain, IRStatus
from regops_shared.models.base import Base, TimestampMixin, UUIDPrimaryKey
from regops_shared.models.cell import domain_enum

ir_status_enum = SAEnum(
    IRStatus, name="ir_status", values_callable=lambda e: [m.value for m in e], native_enum=True
)


class IR(UUIDPrimaryKey, TimestampMixin, Base):
    """One atomic regulatory obligation: one bearer + one modal + one required action.

    ``domain_profile`` selects an extraction **rule set**, not a code path (ADR-0004 decision 3) —
    same tables, same stages, same lifecycle. It is the only place domain divergence lives, which is
    what keeps ``Clause`` domain-neutral.
    """

    __tablename__ = "irs"
    __table_args__ = (Index("ix_irs_status", "status"),)

    domain_profile: Mapped[Domain] = mapped_column(domain_enum, nullable=False)

    bearer: Mapped[str | None] = mapped_column(Text, nullable=True)
    modal: Mapped[str | None] = mapped_column(String(64), nullable=True)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    condition_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    taxonomy_code: Mapped[str | None] = mapped_column(String(64), nullable=True)

    status: Mapped[IRStatus] = mapped_column(ir_status_enum, nullable=False, default=IRStatus.DRAFT)
    #: An amendment re-derives into a **new** IR pointing back here; a locked IR is never mutated
    #: in place (ADR-0004 decision 5).
    supersedes_ir_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("irs.id"), nullable=True)
    stale_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    locked_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    #: Provenance for any row an LLM produced (`.claude/skills/service-endpoint` § LLM seam).
    llm_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    rule_version: Mapped[str | None] = mapped_column(String(32), nullable=True)


class IRCitation(UUIDPrimaryKey, Base):
    """``(document_id, document_version_id, clause_path, effective_date)`` — pinned, not "current".

    ``superseded_at`` is set by the diff stage when an amendment touches the cited path. The row is
    **not** repointed at the new version: rewriting it would silently change the evidence behind an
    obligation an RA already locked, while the audit trail still showed one approved record.
    """

    __tablename__ = "ir_citations"
    __table_args__ = (
        UniqueConstraint(
            "ir_id", "document_version_id", "clause_path", name="uq_ir_citations_target"
        ),
        # The superseded-citation sweep queries by exactly this pair, once per amended clause path.
        Index("ix_ir_citations_version_path", "document_version_id", "clause_path"),
        Index("ix_ir_citations_ir_id", "ir_id"),
    )

    ir_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("irs.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"), nullable=False)
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_versions.id"), nullable=False
    )
    clause_path: Mapped[str] = mapped_column(String(512), nullable=False)
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: Which diff superseded it — the evidence for the flag, so re-verification can show a reviewer
    #: what changed rather than only that something did.
    superseded_by_diff_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("clause_diffs.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )


__all__ = ["IR", "IRCitation", "ir_status_enum"]
