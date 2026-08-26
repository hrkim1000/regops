"""InfoRequirements, their citations, and the extraction run that produced them.

Phase 1.1 created the ``irs`` / ``ir_citations`` shell so that superseded-citation detection had
somewhere to land; **phase 1.2 fills it and adds the three tables ADR-0004's schema names** —
``extraction_runs``, ``clause_classifications`` and ``ir_standard_citations``.

Four invariants are structural rather than conventional:

- **An IR without a citation does not exist** (ADR-0004 decision 2). ``ir_citations.ir_id`` is
  ``NOT NULL``, so a citation cannot float free of an IR; and a *deferred constraint trigger*
  (migration 0004) rejects at commit any ``irs`` row with no citation. Extraction that cannot attach
  ``(document_version_id, clause_path)`` is rejected, not stored with a null citation, and there is
  no draft state for an uncited IR.
- **A citation names an immutable version, never "current"** (ADR-0002 decision 4). The tuple is
  ``(document_id, document_version_id, clause_path, effective_date)`` and it is never rewritten —
  an amendment sets ``superseded_at`` and leaves the original resolvable.
- **The LLM proposes; a human locks** (ADR-0004 decision 4). Extraction writes ``draft``; only an
  ``ra`` moves a row to ``locked``, and only ``locked`` IRs are visible downstream.
- **Amendments re-derive, never mutate** (ADR-0004 decision 5). The old IR is frozen at
  ``superseded`` and the new one points back through ``supersedes_ir_id``.

``ir_standard_citations`` resolves to a deep link and never to stored text — a Tier D standard has
no body anywhere in this system (CLAUDE.md § Architecture rules).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
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
from sqlalchemy.orm import Mapped, mapped_column

from regops_shared.constants import (
    ClassificationKind,
    Domain,
    ExclusionReason,
    ExtractionRunStatus,
    IRStatus,
    RejectionReason,
)
from regops_shared.models.base import Base, TimestampMixin, UUIDPrimaryKey
from regops_shared.models.cell import domain_enum

ir_status_enum = SAEnum(
    IRStatus, name="ir_status", values_callable=lambda e: [m.value for m in e], native_enum=True
)
classification_kind_enum = SAEnum(
    ClassificationKind,
    name="classification_kind",
    values_callable=lambda e: [m.value for m in e],
    native_enum=True,
)
exclusion_reason_enum = SAEnum(
    ExclusionReason,
    name="exclusion_reason",
    values_callable=lambda e: [m.value for m in e],
    native_enum=True,
)
rejection_reason_enum = SAEnum(
    RejectionReason,
    name="rejection_reason",
    values_callable=lambda e: [m.value for m in e],
    native_enum=True,
)
extraction_run_status_enum = SAEnum(
    ExtractionRunStatus,
    name="extraction_run_status",
    values_callable=lambda e: [m.value for m in e],
    native_enum=True,
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

    #: Who refused this draft, why, and when (ADR-0020). Set together with ``status = rejected`` and
    #: cleared by a re-review, the same way the lock triple is.
    #:
    #: The reason is an enum and the note is free text, for the split ``ExclusionReason`` already
    #: makes: the count per reason is a quality signal about the extraction agent — a jump in
    #: ``not_an_obligation`` is a classification regression showing up at review time — while the
    #: particulars of one refusal are a human judgement that no enum should pretend to hold.
    rejected_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[RejectionReason | None] = mapped_column(
        rejection_reason_enum, nullable=True
    )
    rejection_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: Provenance for any row an LLM produced (`.claude/skills/service-endpoint` § LLM seam).
    #:
    #: **Nullable in the column, mandatory in practice.** They cannot be ``NOT NULL`` because 1.1
    #: shipped the table without them populated, but every row 1.2 writes carries all four, and the
    #: acceptance suite asserts no ``irs`` row exists with a null ``llm_provider``/``llm_model``.
    llm_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    rule_version: Mapped[str | None] = mapped_column(String(32), nullable=True)

    #: The run that produced this row. Together with ``rule_version``/``prompt_version`` it answers
    #: "under what regime was this obligation asserted" without joining through the citation.
    extraction_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("extraction_runs.id", ondelete="SET NULL"), nullable=True
    )

    @property
    def is_visible(self) -> bool:
        """Whether downstream consumers may read this IR (ADR-0004 decision 4).

        A property rather than a column: ``status`` already answers it, and a second stored flag
        would drift the moment someone updated one and not the other.
        """
        return self.status is IRStatus.LOCKED


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


class IRStandardCitation(UUIDPrimaryKey, Base):
    """An IR that rests on a Tier D standard, recorded as a **reference and nothing else**.

    ``standard_references`` holds a number, an edition and a deep link — no body text, and no column
    body text could occupy (ADR-0002 decision 2). So this table lets an IR say *"and it must meet
    ISO 14971"* while storing nothing the licence forbids. It is a second citation kind, not a
    substitute: the IR still carries at least one clause citation, because the *obligation* comes
    from the regulation even when the *specification* comes from the standard.
    """

    __tablename__ = "ir_standard_citations"
    __table_args__ = (
        UniqueConstraint("ir_id", "standard_reference_id", name="uq_ir_standard_citations_target"),
        Index("ix_ir_standard_citations_ir_id", "ir_id"),
    )

    ir_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("irs.id", ondelete="CASCADE"), nullable=False
    )
    standard_reference_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("standard_references.id", ondelete="RESTRICT"), nullable=False
    )

    #: How the clause named the standard, verbatim — "IEC 62304에 따라". Kept because resolving a
    #: reference is a claim, and a reviewer needs to see the words that were resolved.
    reference_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )


class ExtractionRun(UUIDPrimaryKey, Base):
    """One pass of the Requirement Extraction agent over one document version.

    This is the provenance anchor ADR-0008 requires of an **agent**: it invokes an LLM, writes rows
    carrying provenance, and its output cannot be trusted without a separate check. The run records
    what regime produced the rows so a later reader can reproduce or discount them.

    ``temperature`` is stored rather than assumed. ADR-0017 pins it to 0 and treats drift as a
    regression — a claim that is only checkable if the value used is on the row rather than in a
    constant that has since been edited.
    """

    __tablename__ = "extraction_runs"
    __table_args__ = (
        Index("ix_extraction_runs_version", "document_version_id", "started_at"),
        Index("ix_extraction_runs_status", "status"),
        # Bare suffix: the `ck` naming convention in ``models.base`` expands it to
        # ``ck_extraction_runs_counts_nonneg``, and passing the full name would double the prefix.
        CheckConstraint(
            "clauses_seen >= 0 AND irs_written >= 0 AND rejected_uncited >= 0",
            name="counts_nonneg",
        ),
    )

    document_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False
    )
    #: Which rule set ran. A version claimed by both gated cells is extracted once per domain, so
    #: the SaMD and Cosmetic readings of a shared instrument are separate runs and separate IRs.
    domain_profile: Mapped[Domain] = mapped_column(domain_enum, nullable=False)

    rule_version: Mapped[str] = mapped_column(String(32), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    llm_provider: Mapped[str] = mapped_column(String(32), nullable=False)
    llm_model: Mapped[str] = mapped_column(String(64), nullable=False)
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)

    status: Mapped[ExtractionRunStatus] = mapped_column(
        extraction_run_status_enum, nullable=False, default=ExtractionRunStatus.RUNNING
    )

    clauses_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    irs_written: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Proposals discarded because no ``(document_version_id, clause_path)`` could be attached.
    #: Counted, never stored as a null-citation row (ADR-0004 decision 2) — a rejection rate that
    #: climbs is a prompt regression, and it is invisible if rejections leave no trace.
    rejected_uncited: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: Bumped at every incremental checkpoint, so ``running`` can be checked rather than believed.
    #: ``started_at`` cannot do this job: it never moves, so a run killed after one clause looks
    #: exactly like one still working three hours in. See ``extraction_run_is_live``.
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<ExtractionRun {self.domain_profile} {self.status} irs={self.irs_written}>"


class ClauseClassification(UUIDPrimaryKey, Base):
    """*This clause was examined.* One row per (clause, domain profile) — ADR-0004 decision 6.

    Keyed per domain, not per clause alone: 인체적용제품의 위해성평가에 관한 규정 is claimed by both
    gated cells, and a clause that bears an obligation under the SaMD taxonomy may bear none under
    the Cosmetic one. One shared row would force the two readings to agree.

    An ``excluded`` row without a reason is rejected by a CHECK constraint. "Excluded" with no
    reason is indistinguishable from "skipped", and the whole point of this table is that the
    difference is on the record.
    """

    __tablename__ = "clause_classifications"
    __table_args__ = (
        UniqueConstraint("clause_id", "domain_profile", name="uq_clause_classifications_target"),
        Index("ix_clause_classifications_run", "extraction_run_id"),
        Index("ix_clause_classifications_kind", "kind"),
        CheckConstraint(
            "(kind = 'excluded') = (exclusion_reason IS NOT NULL)",
            name="reason",
        ),
    )

    clause_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clauses.id", ondelete="CASCADE"), nullable=False
    )
    domain_profile: Mapped[Domain] = mapped_column(domain_enum, nullable=False)

    kind: Mapped[ClassificationKind] = mapped_column(classification_kind_enum, nullable=False)
    exclusion_reason: Mapped[ExclusionReason | None] = mapped_column(
        exclusion_reason_enum, nullable=True
    )
    #: Free-text detail *beside* the enum, never instead of it. The enum is what aggregates.
    exclusion_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    extraction_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("extraction_runs.id", ondelete="SET NULL"), nullable=True
    )
    #: The agent, or the ``ra`` who overrode it. Null means the agent — a human decision always
    #: names the human.
    classified_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    classified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<ClauseClassification {self.kind} {self.exclusion_reason or ''}>"


__all__ = [
    "IR",
    "ClauseClassification",
    "ExtractionRun",
    "IRCitation",
    "IRStandardCitation",
    "classification_kind_enum",
    "exclusion_reason_enum",
    "extraction_run_status_enum",
    "ir_status_enum",
]
