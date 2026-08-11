"""The retrieval index and the answer log — everything ``assistant`` owns.

This is the layer that carries two of the six Phase 1 gates outright: citation accuracy ≥ 90% and
hallucination rate ≤ 2%. Neither is won by generating better prose, so four properties here are
structural rather than conventional:

- **Embeddings live in ``assistant``, not beside the clauses they cover.** Coupling the embedding
  lifecycle to the clause lifecycle would make swapping the model a ``regulation`` migration, and
  the model is the replaceable part (CLAUDE.md § Architecture rules). ``clause_embeddings``
  references ``clauses`` and is owned here.
- **Answer citations are not IR citations** (ADR-0006 decision 10). They share a shape and nothing
  else: an amended clause makes an IR *stale* and re-derived, and an answer *superseded* and
  re-verified. Merging the two would couple the answer log to the obligation model and let one
  amendment rewrite history in both.
- **A citation names an immutable version, never "current".** The tuple is
  ``(document_id, document_version_id, clause_path, effective_date)``; an amendment sets
  ``superseded_at`` and leaves the original resolvable, so a stored answer's citation still resolves
  to the text it was written against.
- **"Needs verification" is a stored outcome with a stored reason** (decision 7). The rate is a
  two-sided monitored metric, and a rate whose reasons cannot be counted tells you it moved without
  telling you why.

``queries`` and ``answers`` carry ``tenant_id`` from their first migration (ADR-0005 decision 2)
even though tenancy arrives in Phase 3 — backfilling a tenant column onto an answer log is how
answers end up attributed to the wrong customer.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
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
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from regops_shared.constants import (
    EMBEDDING_DIM,
    AnswerStatus,
    EmbeddingScope,
    VerificationVerdict,
)
from regops_shared.models.base import Base, UUIDPrimaryKey, utcnow

embedding_scope_enum = SAEnum(
    EmbeddingScope,
    name="embedding_scope",
    values_callable=lambda e: [m.value for m in e],
    native_enum=True,
)
answer_status_enum = SAEnum(
    AnswerStatus,
    name="answer_status",
    values_callable=lambda e: [m.value for m in e],
    native_enum=True,
)
verification_verdict_enum = SAEnum(
    VerificationVerdict,
    name="verification_verdict",
    values_callable=lambda e: [m.value for m in e],
    native_enum=True,
)


class ClauseEmbedding(UUIDPrimaryKey, Base):
    """One passage vector. The passage is a 조; the citation it leads to is finer (decision 1).

    ``child_clause_paths`` is what makes the two granularities work together: the retrieved passage
    carries the addresses of every clause rolled into it, so generation can cite 제8조제2항제3호
    while retrieval only ever had to match 제8조.

    ``passage`` is stored rather than reassembled at query time. It is the exact text the vector was
    computed from, so a retrieval result can be shown to a reviewer without re-walking the clause
    tree and hoping the walk still produces the same thing.
    """

    __tablename__ = "clause_embeddings"
    __table_args__ = (
        UniqueConstraint("clause_id", "fragment_index", name="uq_clause_embeddings_fragment"),
        Index("ix_clause_embeddings_version", "document_version_id"),
        Index("ix_clause_embeddings_model", "model"),
        CheckConstraint("fragment_index >= 0", name="fragment_index_nonneg"),
    )

    clause_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clauses.id", ondelete="CASCADE"), nullable=False
    )
    #: Denormalized from the clause so retrieval can scope to a pinned version without joining back
    #: across the service seam on every candidate row.
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False
    )

    scope: Mapped[EmbeddingScope] = mapped_column(embedding_scope_enum, nullable=False)
    #: 0 for a whole 조; 1, 2, … for the fragments a long one was split into at 항 boundaries.
    fragment_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    passage: Mapped[str] = mapped_column(Text, nullable=False)
    child_clause_paths: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)

    #: ``sha256`` of the passage. Re-embedding compares this before spending a model call, so a
    #: re-run over an unchanged version costs one query per passage rather than one inference.
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    dim: Mapped[int] = mapped_column(Integer, nullable=False, default=EMBEDDING_DIM)
    #: How the passage was assembled. A model swap and an assembly change both invalidate a vector,
    #: and only one of them is visible in ``model``.
    passage_version: Mapped[str] = mapped_column(String(32), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<ClauseEmbedding {self.scope} {self.clause_id}#{self.fragment_index}>"


class Query(UUIDPrimaryKey, Base):
    """One question asked, with the scope it was asked in.

    ``cell_id`` is **required**. Retrieval is cell-scoped (ADR-0006 decision 9) because a cosmetic
    question answered from device regulation is a confident wrong answer — the worst failure this
    product can produce — and a nullable cell would make "unscoped" the accidental default.
    ``cross_cell`` is the explicit opt-in, stored so that a cross-domain golden-set item can be told
    apart from a scoped one after the fact.
    """

    __tablename__ = "queries"
    __table_args__ = (
        Index("ix_queries_cell_asked_at", "cell_id", "asked_at"),
        Index("ix_queries_tenant_id", "tenant_id"),
    )

    tenant_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    cell_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cells.id"), nullable=False)
    cross_cell: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    text: Mapped[str] = mapped_column(Text, nullable=False)
    asked_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    asked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Query {self.text[:40]!r}>"


class Answer(UUIDPrimaryKey, Base):
    """What was answered, on what evidence, and how sure the system is.

    ``effective_date_scope`` is not decoration. Every answer states the version and date it relied
    on — *"시행일 2026-04-02 기준"* (decision 8) — and ``straddles_effective_date`` records the case
    the API's per-clause 조문시행일자 makes routine: a document holding in-force provisions beside
    amended-but-not-yet-effective ones. Where retrieved clauses straddle that boundary the answer
    says so rather than picking one, because silently mixing them is wrong in the way that costs a
    customer an approval.
    """

    __tablename__ = "answers"
    __table_args__ = (
        Index("ix_answers_query_id", "query_id"),
        Index("ix_answers_status", "status"),
        Index("ix_answers_tenant_id", "tenant_id"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
    )

    query_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("queries.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)

    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[AnswerStatus] = mapped_column(answer_status_enum, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    #: Why no answer was given, from the closed :class:`~regops_shared.constants.NoAnswerReason`
    #: inventory. Null on an ``answered`` row; a counted value on every other, so the monitored
    #: "needs verification" rate can be read by cause rather than only by height.
    no_answer_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)

    #: The versions retrieval was pinned to — never "latest" implicitly. An answer that cannot name
    #: its versions cannot be re-checked against them.
    document_version_scope: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(PGUUID(as_uuid=True)), nullable=False, default=list
    )
    effective_date_scope: Mapped[date | None] = mapped_column(Date, nullable=True)
    straddles_effective_date: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    llm_provider: Mapped[str] = mapped_column(String(32), nullable=False)
    llm_model: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    retrieval_version: Mapped[str] = mapped_column(String(32), nullable=False)

    #: Set when an amendment touches a clause this answer cites. The answer is **not** rewritten:
    #: it is a record of what was said on the evidence of the day, and re-verification produces a
    #: new answer rather than editing the old one.
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    @property
    def is_final(self) -> bool:
        """Whether this may be shown to a user as an answer rather than as a referral."""
        return self.status is AnswerStatus.ANSWERED

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Answer {self.status} conf={self.confidence:.2f}>"


class AnswerCitation(UUIDPrimaryKey, Base):
    """``(document_id, document_version_id, clause_path, effective_date)`` — per claim.

    ``claim_index`` ties the citation to the sentence it supports rather than to the answer as a
    whole. The verification pass judges claims one at a time (decision 6), and a citation attached
    only to the answer would make "which claim is unsupported" unanswerable.
    """

    __tablename__ = "answer_citations"
    __table_args__ = (
        UniqueConstraint(
            "answer_id",
            "claim_index",
            "document_version_id",
            "clause_path",
            name="uq_answer_citations_target",
        ),
        Index("ix_answer_citations_answer_id", "answer_id"),
        # The superseded sweep queries by exactly this pair, once per amended clause path.
        Index("ix_answer_citations_version_path", "document_version_id", "clause_path"),
    )

    answer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("answers.id", ondelete="CASCADE"), nullable=False
    )
    claim_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"), nullable=False)
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_versions.id"), nullable=False
    )
    clause_path: Mapped[str] = mapped_column(String(512), nullable=False)
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    superseded_by_diff_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("clause_diffs.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<AnswerCitation {self.clause_path}>"


class VerificationResult(UUIDPrimaryKey, Base):
    """The evidence-verification agent's verdict on one claim (ADR-0006 decision 6).

    The verifier sees the claim and the cited clause text — **not** the question, which biases
    toward agreement. It can reject, and a rejection forces the answer to "needs verification"
    rather than appending a caveat to a wrong answer.
    """

    __tablename__ = "verification_results"
    __table_args__ = (
        UniqueConstraint("answer_id", "claim_index", name="uq_verification_results_claim"),
        Index("ix_verification_results_verdict", "verdict"),
    )

    answer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("answers.id", ondelete="CASCADE"), nullable=False
    )
    claim_index: Mapped[int] = mapped_column(Integer, nullable=False)

    verdict: Mapped[VerificationVerdict] = mapped_column(verification_verdict_enum, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    verifier_provider: Mapped[str] = mapped_column(String(32), nullable=False)
    verifier_model: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<VerificationResult claim={self.claim_index} {self.verdict}>"


__all__ = [
    "Answer",
    "AnswerCitation",
    "ClauseEmbedding",
    "Query",
    "VerificationResult",
    "answer_status_enum",
    "embedding_scope_enum",
    "verification_verdict_enum",
]
