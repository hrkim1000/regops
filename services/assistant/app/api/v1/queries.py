"""Asking a question, reading the answer, and the two things nobody should have to go digging for.

Four surfaces, and three of them exist because of what ADR-0006 says an answer *is*:

- **Ask.** ``202`` with an id, because answering is model-bound: one generation plus one
  verification per claim. The question row is written synchronously so the caller has something to
  poll from the moment it asked.
- **Read.** The answer arrives with its citations, its per-claim verdicts and its provenance,
  because an answer without them is exactly the unverifiable output this product exists not to
  produce.
- **The superseded queue.** Surfaced as a product feature, not a maintenance chore: *"three answers
  you have relied on rest on clauses that have since been amended"* is the alert an RA wants, and
  burying it in a cron job would waste the one thing the citation model buys.
- **The rate.** "Needs verification" per domain, beside the two gates it guards. A system that
  refuses everything passes citation accuracy and hallucination rate cleanly, so those gates are not
  self-guarding — this endpoint is what makes that visible (decision 7).
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi import Query as QueryParam
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy import text as sql_text

from regops_shared.api import Meta, ok
from regops_shared.auth import Principal, get_current_principal
from regops_shared.constants import AnswerStatus
from regops_shared.db import AsyncSession, get_db

from ...models import Answer, AnswerCitation, Query, VerificationResult

router = APIRouter(prefix="/api/v1", tags=["assistant"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[Principal, Depends(get_current_principal)]

ANSWER_PAGE_SIZE = 50
ANSWER_PAGE_SIZE_MAX = 200


class AskRequest(BaseModel):
    """A question, in the body rather than the query string.

    An RA's real question is a sentence, sometimes a paragraph quoted out of a submission dossier.
    Query strings have length limits that a proxy enforces by truncating, and a truncated question
    is answered confidently against the half that survived.
    """

    text: str = Field(min_length=2, description="The question, as asked")
    cell_id: uuid.UUID = Field(description="The cell this question is asked in")
    cross_cell: bool = Field(
        default=False,
        description=(
            "Search beyond the cell. Explicit by design — a cosmetic question answered from "
            "device regulation is a confident wrong answer (ADR-0006 decision 9)"
        ),
    )


@router.post("/queries", status_code=status.HTTP_202_ACCEPTED)
async def ask_question(body: AskRequest, db: DbSession, principal: CurrentUser) -> dict[str, Any]:
    """Record the question and answer it out of band.

    ``cell_id`` is required rather than inferred. Cell scope is the one retrieval bound whose
    absence produces a *plausible* wrong answer instead of an empty one, so it is never defaulted.
    """
    query = Query(
        cell_id=body.cell_id,
        cross_cell=body.cross_cell,
        text=body.text,
        asked_by=principal.id,
    )
    db.add(query)
    # Commit BEFORE dispatching. Dispatching first is a race the worker wins often enough to
    # matter: it picks the task up, finds no row, logs `answer.unknown_query` and returns
    # *success*, leaving a question that will never be answered, with no retry and no signal —
    # observed repeatedly during the first phase 1.6 harness run.
    #
    # The reverse failure is strictly better. A crash between these two statements leaves a
    # committed question with no worker, which is visible (`/qa/queries/{id}` renders a pending
    # question with an elapsed clock) and re-dispatchable, because the row is there to dispatch
    # for. An orphaned task is neither.
    await db.commit()

    from ...celery_app import celery_app

    task = celery_app.send_task("assistant.answer_query", args=[str(query.id)], queue="assistant")
    return {
        "code": status.HTTP_202_ACCEPTED,
        "status": "success",
        "message": "Question accepted",
        "data": {"id": str(query.id), "task_id": task.id},
        "meta": None,
    }


@router.get("/queries/{query_id}")
async def get_query(query_id: uuid.UUID, db: DbSession, _: CurrentUser) -> dict[str, Any]:
    """The question and its answer, or the question alone while the answer is still coming."""
    query = await db.get(Query, query_id)
    if query is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Query not found")

    answer = await db.scalar(
        select(Answer).where(Answer.query_id == query_id).order_by(Answer.created_at.desc())
    )
    payload: dict[str, Any] = {
        "id": str(query.id),
        "text": query.text,
        "cell_id": str(query.cell_id),
        "cross_cell": query.cross_cell,
        "asked_at": query.asked_at.isoformat(),
        "answer": None,
    }
    if answer is not None:
        payload["answer"] = await _answer_out(db, answer)
    return ok(payload)


@router.get("/answers/{answer_id}")
async def get_answer(answer_id: uuid.UUID, db: DbSession, _: CurrentUser) -> dict[str, Any]:
    """One answer with its citations, its verdicts and its provenance."""
    answer = await db.get(Answer, answer_id)
    if answer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Answer not found")
    query = await db.get(Query, answer.query_id)
    payload = await _answer_out(db, answer)
    payload["question"] = query.text if query else None
    return ok(payload)


@router.get("/answers")
async def list_answers(
    db: DbSession,
    _: CurrentUser,
    answer_status: Annotated[
        list[AnswerStatus] | None, QueryParam(alias="status", description="Filter by status")
    ] = None,
    superseded: Annotated[
        bool | None,
        QueryParam(
            description=(
                "true returns the superseded queue: answers resting on clauses that have since "
                "been amended"
            )
        ),
    ] = None,
    cell_id: uuid.UUID | None = None,
    page: int = QueryParam(1, ge=1),
    page_size: int = QueryParam(ANSWER_PAGE_SIZE, ge=1, le=ANSWER_PAGE_SIZE_MAX),
) -> dict[str, Any]:
    """Answers, newest first. ``superseded=true`` is the review queue an amendment creates."""
    stmt = select(Answer)
    count_stmt = select(func.count()).select_from(Answer)

    if answer_status:
        stmt = stmt.where(Answer.status.in_(tuple(answer_status)))
        count_stmt = count_stmt.where(Answer.status.in_(tuple(answer_status)))
    if superseded is not None:
        predicate = (
            Answer.superseded_at.is_not(None) if superseded else Answer.superseded_at.is_(None)
        )
        stmt, count_stmt = stmt.where(predicate), count_stmt.where(predicate)
    if cell_id is not None:
        scoped = select(Query.id).where(Query.cell_id == cell_id)
        stmt = stmt.where(Answer.query_id.in_(scoped))
        count_stmt = count_stmt.where(Answer.query_id.in_(scoped))

    total = await db.scalar(count_stmt) or 0
    rows = list(
        await db.scalars(
            stmt.order_by(Answer.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
    )
    # A summary shape, and one grouped query for the citation counts rather than two per row. At
    # page_size 200 the per-row version was 400 round trips to render a list nobody reads in full.
    counts = await _citation_counts(db, [row.id for row in rows])
    return ok(
        [_answer_summary(row, counts.get(row.id, (0, 0))) for row in rows],
        meta=Meta(page=page, page_size=page_size, total=total),
    )


@router.get("/metrics/answers")
async def answer_metrics(db: DbSession, _: CurrentUser) -> dict[str, Any]:
    """The "needs verification" rate per domain, beside the counts it is derived from.

    Two-sided by design (ADR-0006 decision 7). Near 0% means the confidence threshold is too
    permissive and the hallucination gate is about to be missed; too high means the product is
    unusable however honest it is. Treat a sudden move either way as a regression — which is only
    possible if the number is reported at all, per domain, from the first golden-set run.
    """
    overall = list(await db.execute(select(func.count(), Answer.status).group_by(Answer.status)))
    # `cells` belongs to `regulation`, so the per-domain split is a raw-SQL read across the seam
    # rather than an ORM join through another service's model (CLAUDE.md § Table ownership).
    per_domain = list(await db.execute(_DOMAIN_COUNTS))
    reasons = list(
        await db.execute(
            select(func.count(), Answer.no_answer_reason)
            .where(Answer.no_answer_reason.is_not(None))
            .group_by(Answer.no_answer_reason)
        )
    )

    return ok(
        {
            "overall": _rate_block({row[1].value: row[0] for row in overall}),
            "domains": [
                {"domain": domain, **_rate_block(_counts_from(per_domain, domain))}
                for domain in sorted({row[0] for row in per_domain})
            ],
            "reasons": {row[1]: row[0] for row in reasons},
        }
    )


# --- shaping ---------------------------------------------------------------------------------

_DOMAIN_COUNTS = sql_text(
    """
    SELECT c.domain::text AS domain, a.status::text AS status, count(*) AS n
    FROM answers a
    JOIN queries q ON q.id = a.query_id
    JOIN cells c ON c.id = q.cell_id
    GROUP BY 1, 2
    """
)


def _counts_from(rows: list[Any], domain: str) -> dict[str, int]:
    return {row[1]: row[2] for row in rows if row[0] == domain}


def _rate_block(counts: dict[str, int]) -> dict[str, Any]:
    total = sum(counts.values())
    needs = counts.get(AnswerStatus.NEEDS_VERIFICATION.value, 0)
    review = counts.get(AnswerStatus.NEEDS_REVIEW.value, 0)
    return {
        "total": total,
        "answered": counts.get(AnswerStatus.ANSWERED.value, 0),
        "needs_verification": needs,
        "needs_review": review,
        # Rounded to four places rather than presented raw: this is a monitored rate, and a value
        # that changes in the twelfth decimal on every run is noise wearing a signal's clothes.
        "needs_verification_rate": round(needs / total, 4) if total else None,
        "needs_review_rate": round(review / total, 4) if total else None,
    }


async def _citation_counts(
    db: AsyncSession, answer_ids: list[uuid.UUID]
) -> dict[uuid.UUID, tuple[int, int]]:
    """``{answer_id: (citations, superseded)}`` for a whole page in one query."""
    if not answer_ids:
        return {}
    rows = await db.execute(
        select(
            AnswerCitation.answer_id,
            func.count(),
            func.count().filter(AnswerCitation.superseded_at.is_not(None)),
        )
        .where(AnswerCitation.answer_id.in_(answer_ids))
        .group_by(AnswerCitation.answer_id)
    )
    return {row[0]: (row[1], row[2]) for row in rows}


def _answer_summary(answer: Answer, counts: tuple[int, int]) -> dict[str, Any]:
    """A list row. Citations and verdicts are counted here and enumerated on the detail endpoint.

    The counts are not decoration: on the superseded queue, *"2 of 3 citations have moved"* is the
    whole reason a row is in the list.
    """
    citations, superseded = counts
    return {
        "id": str(answer.id),
        "query_id": str(answer.query_id),
        "status": answer.status.value,
        "is_final": answer.is_final,
        "confidence": answer.confidence,
        "no_answer_reason": answer.no_answer_reason,
        "effective_date_scope": (
            answer.effective_date_scope.isoformat() if answer.effective_date_scope else None
        ),
        "straddles_effective_date": answer.straddles_effective_date,
        "superseded_at": answer.superseded_at.isoformat() if answer.superseded_at else None,
        "citation_count": citations,
        "superseded_citation_count": superseded,
        "created_at": answer.created_at.isoformat(),
    }


async def _answer_out(db: AsyncSession, answer: Answer) -> dict[str, Any]:
    citations = list(
        await db.scalars(
            select(AnswerCitation)
            .where(AnswerCitation.answer_id == answer.id)
            .order_by(AnswerCitation.claim_index, AnswerCitation.clause_path)
        )
    )
    verdicts = list(
        await db.scalars(
            select(VerificationResult)
            .where(VerificationResult.answer_id == answer.id)
            .order_by(VerificationResult.claim_index)
        )
    )
    return {
        "id": str(answer.id),
        "query_id": str(answer.query_id),
        "text": answer.text,
        "status": answer.status.value,
        "is_final": answer.is_final,
        "confidence": answer.confidence,
        "no_answer_reason": answer.no_answer_reason,
        "effective_date_scope": (
            answer.effective_date_scope.isoformat() if answer.effective_date_scope else None
        ),
        "straddles_effective_date": answer.straddles_effective_date,
        "document_version_scope": [str(value) for value in answer.document_version_scope],
        "superseded_at": answer.superseded_at.isoformat() if answer.superseded_at else None,
        "citations": [
            {
                "claim_index": citation.claim_index,
                "document_id": str(citation.document_id),
                "document_version_id": str(citation.document_version_id),
                "clause_path": citation.clause_path,
                "effective_date": (
                    citation.effective_date.isoformat() if citation.effective_date else None
                ),
                "superseded_at": (
                    citation.superseded_at.isoformat() if citation.superseded_at else None
                ),
            }
            for citation in citations
        ],
        "verification": [
            {
                "claim_index": verdict.claim_index,
                "verdict": verdict.verdict.value,
                "reason": verdict.reason,
                "verifier_provider": verdict.verifier_provider,
                "verifier_model": verdict.verifier_model,
            }
            for verdict in verdicts
        ],
        "provenance": {
            "llm_provider": answer.llm_provider,
            "llm_model": answer.llm_model,
            "prompt_version": answer.prompt_version,
            "retrieval_version": answer.retrieval_version,
        },
    }


__all__ = ["router"]
