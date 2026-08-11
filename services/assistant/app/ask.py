"""Question in, answer or refusal out — the orchestration ADR-0006 describes end to end.

    retrieve (pipeline) → generate (agent) → verify (agent) → score → route

Every step can stop the chain, and stopping it is a **product output**, not an error path. "Needs
verification" is the promise in RegOps.md kept: no unsourced answer is ever generated. Its rate is a
monitored two-sided metric (decision 7) — near 0% means the threshold is too permissive and the
hallucination gate is about to be missed; too high means the product is unusable however honest it
is — so the reason for every refusal is stored from a closed inventory, not written as prose.

Confidence weights verification above retrieval on purpose. Mis-citation is the hallucination class
that survives every structural check, so how the verifier voted has to outweigh how well retrieval
scored; a well-retrieved passage that does not support the claim is exactly the failure this layer
exists to catch.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date

import structlog
from sqlalchemy.orm import Session

from regops_shared.constants import (
    ANSWER_CONFIDENCE_THRESHOLD,
    ANSWER_PROMPT_VERSION,
    CONFIDENCE_RETRIEVAL_WEIGHT,
    CONFIDENCE_VERIFICATION_WEIGHT,
    RETRIEVAL_TOP_K,
    RETRIEVAL_VERSION,
    VERIFICATION_PROMPT_VERSION,
    AnswerStatus,
    NoAnswerReason,
)
from regops_shared.llm import LLMClient, get_llm_client

from .generate import Claim, GenerationResult, generate
from .models import Answer, AnswerCitation, Query, VerificationResult
from .retrieval import RetrievalResult, retrieve
from .store import cell_ids_for, clauses_by_path, versions_in_scope
from .verify import ClaimVerdict, rejected, verification_score, verify_claims

log = structlog.get_logger(__name__)

#: How an answer states the evidence it relied on (ADR-0006 decision 8). Rendered into the answer
#: text rather than left to a caller: an answer that travels without its effective date is an answer
#: that will eventually be read against the wrong version of the law.
EFFECTIVE_DATE_NOTICE: dict[str, str] = {
    "ko": "시행일 {date} 기준.",
    "en": "As of effective date {date}.",
}

#: Said out loud whenever the retrieved clauses do not share one effective date. Never resolved
#: silently — mixing in-force and not-yet-effective provisions is wrong in the way that costs a
#: customer an approval.
STRADDLE_NOTICE: dict[str, str] = {
    "ko": (
        "주의: 근거 조문의 시행일이 일치하지 않습니다. 시행 중인 조문과 개정되었으나 아직 "
        "시행되지 않은 조문이 함께 검색되었습니다."
    ),
    "en": (
        "Caution: the cited clauses do not share one effective date. Provisions in force and "
        "provisions amended but not yet effective were both retrieved."
    ),
}


@dataclass(slots=True)
class AnswerOutcome:
    """The persisted result, plus what a caller needs without re-querying."""

    query_id: uuid.UUID
    answer_id: uuid.UUID
    status: AnswerStatus
    confidence: float
    text: str
    no_answer_reason: NoAnswerReason | None = None
    straddles_effective_date: bool = False
    effective_date_scope: date | None = None
    citations: list[tuple[int, uuid.UUID, str]] = field(default_factory=list)
    verdicts: list[ClaimVerdict] = field(default_factory=list)

    @property
    def is_final(self) -> bool:
        return self.status is AnswerStatus.ANSWERED


def ask(
    session: Session,
    *,
    question: str,
    cell_id: uuid.UUID,
    cross_cell: bool = False,
    asked_by: uuid.UUID | None = None,
    tenant_id: uuid.UUID | None = None,
    version_ids: list[uuid.UUID] | None = None,
    client: LLMClient | None = None,
    top_k: int = RETRIEVAL_TOP_K,
    today: date | None = None,
) -> AnswerOutcome:
    """Record the question, then answer it. The direct entry point for tests and batch runs."""
    query = Query(
        tenant_id=tenant_id,
        cell_id=cell_id,
        cross_cell=cross_cell,
        text=question,
        asked_by=asked_by,
    )
    session.add(query)
    session.flush()
    return answer_query(
        session, query, version_ids=version_ids, client=client, top_k=top_k, today=today
    )


def answer_query(
    session: Session,
    query: Query,
    *,
    version_ids: list[uuid.UUID] | None = None,
    client: LLMClient | None = None,
    top_k: int = RETRIEVAL_TOP_K,
    today: date | None = None,
) -> AnswerOutcome:
    """Answer an already-recorded question, or refuse with a recorded reason. Commits.

    Split from :func:`ask` because the API records the question synchronously and answers it out of
    band: the caller gets an id it can poll immediately, and the model-bound work runs on the
    worker. A question that was asked is worth recording even if the answer never arrives.
    """
    client = client or get_llm_client()
    today = today or date.today()
    question = query.text

    versions = versions_in_scope(
        session,
        cell_ids=cell_ids_for(session, cell_id=query.cell_id, cross_cell=query.cross_cell),
        today=today,
        version_ids=version_ids,
    )
    retrieval = retrieve(
        session, query=question, versions=versions, client=client, top_k=top_k, today=today
    )

    if retrieval.empty:
        return _refuse(
            session,
            query=query,
            retrieval=retrieval,
            client=client,
            reason=NoAnswerReason.NO_RETRIEVAL,
        )

    try:
        generation = generate(client, question=question, retrieval=retrieval)
    except Exception as exc:
        # A model that times out or refuses the connection is a *recorded* outcome, not a lost
        # question. Letting it propagate leaves the query row with no answer at all: the asker
        # watches a spinner until the poll ceiling, and the monitored "needs verification" rate
        # silently excludes every failure — which is the one direction that makes it look healthy.
        log.warning("ask.generation_failed", query=str(query.id), error=str(exc))
        return _refuse(
            session,
            query=query,
            retrieval=retrieval,
            client=client,
            reason=NoAnswerReason.MODEL_UNAVAILABLE,
        )

    if not generation.usable:
        return _refuse(
            session,
            query=query,
            retrieval=retrieval,
            client=client,
            reason=generation.reason or NoAnswerReason.NO_CITATION,
            generation=generation,
        )

    evidence = clauses_by_path(
        session,
        version_ids=[version.version_id for version in retrieval.versions],
        clause_paths=[
            citation.clause_path for claim in generation.claims for citation in claim.citations
        ],
    )
    try:
        verdicts = verify_claims(client, claims=generation.claims, evidence=evidence)
    except Exception as exc:
        # Same rule on the verification side, and it matters more: an answer whose claims were
        # never checked must not reach a reader as though they had been. Unverified is unsupported.
        log.warning("ask.verification_failed", query=str(query.id), error=str(exc))
        return _refuse(
            session,
            query=query,
            retrieval=retrieval,
            client=client,
            reason=NoAnswerReason.MODEL_UNAVAILABLE,
            generation=generation,
        )

    confidence = score(generation.claims, verdicts=verdicts, retrieval=retrieval)
    status, reason = route(confidence, verdicts=verdicts)

    text = render(generation.answer, retrieval=retrieval)
    answer = _persist(
        session,
        query=query,
        retrieval=retrieval,
        client=client,
        status=status,
        reason=reason,
        confidence=confidence,
        text=text,
        generation=generation,
    )
    _persist_citations(session, answer=answer, claims=generation.claims, retrieval=retrieval)
    _persist_verdicts(session, answer=answer, verdicts=verdicts)
    session.commit()

    log.info(
        "ask.done",
        query=str(query.id),
        status=status.value,
        confidence=round(confidence, 3),
        claims=len(generation.claims),
        straddles=retrieval.straddles_effective_date,
    )
    return AnswerOutcome(
        query_id=query.id,
        answer_id=answer.id,
        status=status,
        confidence=confidence,
        text=text,
        no_answer_reason=reason,
        straddles_effective_date=retrieval.straddles_effective_date,
        effective_date_scope=retrieval.effective_date_scope,
        citations=[
            (index, citation.document_version_id, citation.clause_path)
            for index, claim in enumerate(generation.claims)
            for citation in claim.citations
        ],
        verdicts=verdicts,
    )


# --- scoring and routing ---------------------------------------------------------------------


def route(
    confidence: float, *, verdicts: list[ClaimVerdict]
) -> tuple[AnswerStatus, NoAnswerReason | None]:
    """Where an answer goes once it has been scored.

    Rejection beats confidence, and deliberately so. A verifier that rejected a claim has found the
    mis-citation class (decision 5) — the one that survives every structural check — and no amount
    of retrieval confidence makes an unsupported statement safe to show. The answer becomes "needs
    verification" rather than a hedged answer with a caveat attached.

    Sub-threshold confidence is a *different* outcome from rejection: nothing was found wrong, but
    not enough was found right, so it goes to a human instead of to the user as final.
    """
    if rejected(verdicts):
        return AnswerStatus.NEEDS_VERIFICATION, NoAnswerReason.UNSUPPORTED_CLAIM
    if confidence < ANSWER_CONFIDENCE_THRESHOLD:
        return AnswerStatus.NEEDS_REVIEW, None
    return AnswerStatus.ANSWERED, None


def score(
    claims: list[Claim], *, verdicts: list[ClaimVerdict], retrieval: RetrievalResult
) -> float:
    """Composite confidence in ``[0, 1]``.

    Two components, because they fail independently. Verification asks *does the cited text say
    this*; retrieval rank asks *was this the evidence the question actually pointed at*. An answer
    built from the eighth-ranked passage can be perfectly supported and still be answering a
    neighbouring question, and only the second component notices.
    """
    verified = verification_score(verdicts)
    ranked = _retrieval_score(claims, retrieval=retrieval)
    value = CONFIDENCE_VERIFICATION_WEIGHT * verified + CONFIDENCE_RETRIEVAL_WEIGHT * ranked
    return max(0.0, min(1.0, value))


def _retrieval_score(claims: list[Claim], *, retrieval: RetrievalResult) -> float:
    """Mean normalised rank of the best passage each claim cites. No claims scores zero."""
    if not claims or not retrieval.hits:
        return 0.0
    rank_of: dict[tuple[uuid.UUID, str], int] = {}
    for index, hit in enumerate(retrieval.hits):
        for path in (hit.clause_path, *hit.child_clause_paths):
            rank_of.setdefault((hit.document_version_id, path), index)

    total = 0.0
    for claim in claims:
        ranks = [
            rank_of[key]
            for citation in claim.citations
            if (key := (citation.document_version_id, citation.clause_path)) in rank_of
        ]
        if ranks:
            total += 1.0 - (min(ranks) / len(retrieval.hits))
    return total / len(claims)


# --- rendering -------------------------------------------------------------------------------


def render(answer: str, *, retrieval: RetrievalResult) -> str:
    """Append the version/date statement every answer must carry (decision 8)."""
    language = retrieval.versions[0].language if retrieval.versions else "ko"
    parts = [answer.strip()]
    if retrieval.straddles_effective_date:
        parts.append(STRADDLE_NOTICE.get(language, STRADDLE_NOTICE["en"]))
    if retrieval.effective_date_scope is not None:
        template = EFFECTIVE_DATE_NOTICE.get(language, EFFECTIVE_DATE_NOTICE["en"])
        parts.append(template.format(date=retrieval.effective_date_scope.isoformat()))
    return "\n\n".join(part for part in parts if part)


# --- persistence -----------------------------------------------------------------------------


def _refuse(
    session: Session,
    *,
    query: Query,
    retrieval: RetrievalResult,
    client: LLMClient,
    reason: NoAnswerReason,
    generation: GenerationResult | None = None,
) -> AnswerOutcome:
    """Store a "needs verification" answer. Success, recorded as such, with its cause."""
    answer = _persist(
        session,
        query=query,
        retrieval=retrieval,
        client=client,
        status=AnswerStatus.NEEDS_VERIFICATION,
        reason=reason,
        confidence=0.0,
        text="",
        generation=generation,
    )
    session.commit()
    log.info("ask.needs_verification", query=str(query.id), reason=reason.value)
    return AnswerOutcome(
        query_id=query.id,
        answer_id=answer.id,
        status=AnswerStatus.NEEDS_VERIFICATION,
        confidence=0.0,
        text="",
        no_answer_reason=reason,
        straddles_effective_date=retrieval.straddles_effective_date,
        effective_date_scope=retrieval.effective_date_scope,
    )


def _persist(
    session: Session,
    *,
    query: Query,
    retrieval: RetrievalResult,
    client: LLMClient,
    status: AnswerStatus,
    reason: NoAnswerReason | None,
    confidence: float,
    text: str,
    generation: GenerationResult | None,
) -> Answer:
    """Write the answer row. Provenance is mandatory even on a refusal.

    A refusal is a decision the system made with a particular model at a particular prompt version,
    and "which model refuses too often" is unanswerable if only successes record what produced them.
    """
    answer = Answer(
        query_id=query.id,
        tenant_id=query.tenant_id,
        text=text,
        status=status,
        confidence=confidence,
        no_answer_reason=reason.value if reason else None,
        document_version_scope=[version.version_id for version in retrieval.versions],
        effective_date_scope=retrieval.effective_date_scope,
        straddles_effective_date=retrieval.straddles_effective_date,
        llm_provider=generation.provider if generation and generation.provider else client.provider,
        llm_model=generation.model if generation and generation.model else client.model,
        prompt_version=ANSWER_PROMPT_VERSION,
        retrieval_version=RETRIEVAL_VERSION,
    )
    session.add(answer)
    session.flush()
    return answer


def _persist_citations(
    session: Session, *, answer: Answer, claims: list[Claim], retrieval: RetrievalResult
) -> None:
    """One row per (claim, cited clause), pinned to the version it came from.

    ``document_id`` is resolved from the pinned version rather than from the model's reply — the
    Citation tuple must name a real document, and nothing about it should depend on generation
    having got a second identifier right.
    """
    documents = {version.version_id: version for version in retrieval.versions}
    dates = _effective_dates(retrieval)
    for index, claim in enumerate(claims):
        for citation in claim.citations:
            version = documents.get(citation.document_version_id)
            if version is None:  # pragma: no cover - retrieval only returns pinned versions
                continue
            session.add(
                AnswerCitation(
                    answer_id=answer.id,
                    claim_index=index,
                    document_id=version.document_id,
                    document_version_id=version.version_id,
                    clause_path=citation.clause_path,
                    effective_date=dates.get(
                        (citation.document_version_id, citation.clause_path),
                        version.effective_date,
                    ),
                )
            )
    session.flush()


def _effective_dates(retrieval: RetrievalResult) -> dict[tuple[uuid.UUID, str], date | None]:
    """Per-clause effective dates from the hits — 조문시행일자 where the source states one."""
    out: dict[tuple[uuid.UUID, str], date | None] = {}
    for hit in retrieval.hits:
        out[(hit.document_version_id, hit.clause_path)] = hit.effective_date
    return out


def _persist_verdicts(session: Session, *, answer: Answer, verdicts: list[ClaimVerdict]) -> None:
    for verdict in verdicts:
        session.add(
            VerificationResult(
                answer_id=answer.id,
                claim_index=verdict.claim_index,
                verdict=verdict.verdict,
                reason=verdict.reason,
                verifier_provider=verdict.provider,
                verifier_model=verdict.model,
                prompt_version=VERIFICATION_PROMPT_VERSION,
            )
        )
    session.flush()


__all__ = [
    "EFFECTIVE_DATE_NOTICE",
    "STRADDLE_NOTICE",
    "AnswerOutcome",
    "answer_query",
    "ask",
    "render",
    "route",
    "score",
]
