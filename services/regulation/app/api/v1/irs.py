"""Reading IRs, proving coverage, and the one write a human makes: locking.

Everything the *extractor* writes arrives through the pipeline. This router exposes three things a
person needs and one thing only a person may do:

- **Read draft IRs to review them.** Drafts are visible *here* and nowhere downstream — the review
  queue is exactly the population that has not yet been approved, so hiding it would make locking
  impossible.
- **Prove coverage.** `/coverage` answers "was every clause examined", which is the claim ADR-0004
  decision 6 exists to make checkable. It reports the unclassified remainder rather than assuming
  there is none.
- **Lock.** ``ra`` only, audited, one-way. This is the human assertion that turns a model's proposal
  into an obligation the product will act on, and it is one of the two restricted actions in Phase 1
  (CLAUDE.md § Security).

The default listing filter is ``locked``. A caller that wants drafts asks for them by name, so a
downstream consumer written against this endpoint gets ADR-0004 decision 4's behaviour by default
rather than by remembering to.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from regops_shared.api import Meta, ok
from regops_shared.audit import record
from regops_shared.auth import Principal, get_current_principal, require_roles
from regops_shared.constants import (
    IR_VISIBLE_STATUSES,
    ClassificationKind,
    Domain,
    IRStatus,
    Role,
)
from regops_shared.db import AsyncSession, get_db
from regops_shared.models.base import utcnow

from ...models import (
    IR,
    Clause,
    ClauseClassification,
    DocumentVersion,
    ExtractionRun,
    IRCitation,
)

router = APIRouter(prefix="/api/v1", tags=["regulation"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[Principal, Depends(get_current_principal)]

SERVICE = "regulation"

IR_PAGE_SIZE = 100
IR_PAGE_SIZE_MAX = 500


@router.post("/document-versions/{version_id}/extract", status_code=status.HTTP_202_ACCEPTED)
async def trigger_extraction(
    version_id: uuid.UUID,
    db: DbSession,
    principal: Annotated[Principal, Depends(require_roles([Role.RA, Role.ADMIN]))],
    domain: Domain | None = Query(
        None, description="Limit to one rule set; default is every claiming domain"
    ),
) -> dict[str, Any]:
    """Extract now, out of band. Long work returns 202 and the worker commits incrementally.

    RA-gated even though it writes only drafts: an extraction run spends real model budget over
    every clause of a version, and a `viewer` triggering it repeatedly is a cost incident.
    """
    version = await db.get(DocumentVersion, version_id)
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Version not found")
    if version.parser_version is None:
        # Extraction reads clauses, and an unparsed version has none. Enqueuing anyway would burn a
        # task to log "no clauses" and report success.
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Version has not been parsed; extraction has no clauses to read",
        )

    from ...celery_app import celery_app

    task = celery_app.send_task(
        "regulation.extract_document_version",
        args=[str(version_id), domain.value if domain else None],
        queue="regulation",
    )
    await record(
        db,
        service=SERVICE,
        action="extraction.triggered",
        actor_id=principal.id,
        entity_type="document_version",
        entity_id=version_id,
        payload={"task_id": task.id, "domain": domain.value if domain else None},
    )
    await db.commit()
    return {
        "code": status.HTTP_202_ACCEPTED,
        "status": "success",
        "message": "Extraction enqueued",
        "data": {"id": str(version_id), "task_id": task.id},
        "meta": None,
    }


@router.get("/document-versions/{version_id}/irs")
async def list_irs(
    version_id: uuid.UUID,
    db: DbSession,
    _: CurrentUser,
    ir_status: Annotated[
        list[IRStatus] | None,
        Query(alias="status", description="Default: locked only — what downstream may read"),
    ] = None,
    domain: Domain | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(IR_PAGE_SIZE, ge=1, le=IR_PAGE_SIZE_MAX),
) -> dict[str, Any]:
    """IRs citing this version, newest last.

    Defaults to ``locked`` (:data:`IR_VISIBLE_STATUSES`). A review UI asks for ``draft`` explicitly;
    a consumer that forgets to filter gets the safe answer rather than a queue of unreviewed model
    output presented as obligations.
    """
    version = await db.get(DocumentVersion, version_id)
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Version not found")

    wanted = tuple(ir_status) if ir_status else IR_VISIBLE_STATUSES
    base = (
        select(IR.id)
        .join(IRCitation, IRCitation.ir_id == IR.id)
        .where(IRCitation.document_version_id == version_id, IR.status.in_(wanted))
    )
    if domain is not None:
        base = base.where(IR.domain_profile == domain)
    ids = base.distinct().subquery()

    total = await db.scalar(select(func.count()).select_from(ids)) or 0
    rows = list(
        await db.scalars(
            select(IR)
            .where(IR.id.in_(select(ids.c.id)))
            .order_by(IR.created_at, IR.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    citations = await _citations_by_ir(db, [row.id for row in rows])

    return ok(
        [_ir_out(row, citations.get(row.id, [])) for row in rows],
        meta=Meta(page=page, page_size=page_size, total=total),
    )


@router.get("/irs/{ir_id}")
async def get_ir(ir_id: uuid.UUID, db: DbSession, _: CurrentUser) -> dict[str, Any]:
    """One IR with its citations and its provenance.

    Provenance is not optional detail here: an obligation asserted by a model and never reviewed is
    the artefact an auditor asks about first (ADR-0004 decision 4), so what produced it travels with
    it rather than living in a separate runs table nobody joins.
    """
    ir = await db.get(IR, ir_id)
    if ir is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "IR not found")
    citations = await _citations_by_ir(db, [ir.id])
    run = await db.get(ExtractionRun, ir.extraction_run_id) if ir.extraction_run_id else None
    return ok(_ir_out(ir, citations.get(ir.id, []), run=run))


@router.post("/irs/{ir_id}/lock")
async def lock_ir(
    ir_id: uuid.UUID,
    db: DbSession,
    principal: Annotated[Principal, Depends(require_roles([Role.RA, Role.ADMIN]))],
) -> dict[str, Any]:
    """A human asserts this obligation is correctly extracted. **Restricted and audited.**

    Only from ``draft``. Locking a ``stale`` IR would approve evidence that has already been
    amended; locking a ``superseded`` one would resurrect a record a later IR replaced; re-locking a
    ``locked`` one would overwrite the first signature with a second and lose who actually
    approved it.

    The uncited case is re-checked here rather than trusted from extraction time. It should be
    unreachable — the database's deferred trigger rejects an uncited IR at commit — and the check
    costs one query against the possibility that it is not.
    """
    ir = await db.get(IR, ir_id)
    if ir is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "IR not found")
    if ir.status is not IRStatus.DRAFT:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"IR is '{ir.status.value}'; only a draft IR can be locked",
        )

    cited = await db.scalar(
        select(func.count()).select_from(IRCitation).where(IRCitation.ir_id == ir_id)
    )
    if not cited:  # pragma: no cover - the DB trigger makes this unreachable
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "IR has no citation; an IR without a citation does not exist (ADR-0004 decision 2)",
        )

    ir.status = IRStatus.LOCKED
    ir.locked_by = principal.id
    ir.locked_at = utcnow()
    await record(
        db,
        service=SERVICE,
        action="ir.locked",
        actor_id=principal.id,
        entity_type="ir",
        entity_id=ir_id,
        payload={
            "domain_profile": ir.domain_profile.value,
            "rule_version": ir.rule_version,
            "prompt_version": ir.prompt_version,
            "llm_provider": ir.llm_provider,
            "llm_model": ir.llm_model,
        },
    )
    await db.commit()
    return ok({"id": str(ir_id), "status": ir.status.value, "locked_at": ir.locked_at.isoformat()})


@router.get("/document-versions/{version_id}/coverage")
async def extraction_coverage(
    version_id: uuid.UUID,
    db: DbSession,
    _: CurrentUser,
    domain: Domain | None = None,
) -> dict[str, Any]:
    """Was every clause examined? — ADR-0004 decision 6, as a number rather than an assumption.

    ``unclassified`` is the whole point. "50 IRs from 200 clauses" cannot be told apart from 150
    missed obligations unless the other 150 are on record as examined-and-empty, so this reports the
    remainder explicitly and a non-zero value is a finding, not a rounding detail.
    """
    version = await db.get(DocumentVersion, version_id)
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Version not found")

    clauses = (
        await db.scalar(
            select(func.count()).select_from(Clause).where(Clause.document_version_id == version_id)
        )
        or 0
    )

    per_domain: list[dict[str, Any]] = []
    domains = [domain] if domain is not None else list(Domain)
    for target in domains:
        rows = list(
            await db.execute(
                select(
                    ClauseClassification.kind,
                    ClauseClassification.exclusion_reason,
                    func.count(),
                )
                .join(Clause, Clause.id == ClauseClassification.clause_id)
                .where(
                    Clause.document_version_id == version_id,
                    ClauseClassification.domain_profile == target,
                )
                .group_by(ClauseClassification.kind, ClauseClassification.exclusion_reason)
            )
        )
        if not rows and domain is None:
            # Never extracted under this profile. Reporting it as 100% unclassified would be true
            # but useless noise on the six domains a document was never claimed by.
            continue

        classified = sum(count for _, _, count in rows)
        per_domain.append(
            {
                "domain": target.value,
                "clauses": clauses,
                "classified": classified,
                "unclassified": clauses - classified,
                "obligation_bearing": sum(
                    count
                    for kind, _, count in rows
                    if kind is ClassificationKind.OBLIGATION_BEARING
                ),
                "excluded": sum(
                    count for kind, _, count in rows if kind is ClassificationKind.EXCLUDED
                ),
                "exclusion_reasons": {
                    reason.value: count for _, reason, count in rows if reason is not None
                },
                "complete": classified == clauses,
            }
        )

    return ok({"version_id": str(version_id), "clauses": clauses, "domains": per_domain})


@router.get("/extraction-runs/{run_id}")
async def get_extraction_run(run_id: uuid.UUID, db: DbSession, _: CurrentUser) -> dict[str, Any]:
    """One run's provenance and counters — including how many proposals were rejected uncited."""
    run = await db.get(ExtractionRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Extraction run not found")
    return ok(_run_out(run))


# --- shaping ---------------------------------------------------------------------------------


async def _citations_by_ir(
    db: AsyncSession, ir_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[IRCitation]]:
    """One query for the page, not one per IR."""
    if not ir_ids:
        return {}
    rows = list(
        await db.scalars(
            select(IRCitation).where(IRCitation.ir_id.in_(ir_ids)).order_by(IRCitation.clause_path)
        )
    )
    out: dict[uuid.UUID, list[IRCitation]] = {}
    for row in rows:
        out.setdefault(row.ir_id, []).append(row)
    return out


def _ir_out(
    ir: IR, citations: list[IRCitation], *, run: ExtractionRun | None = None
) -> dict[str, Any]:
    """One obligation.

    The citation list leads the provenance block because that is the reading order: *what does this
    require, on what authority, and who said so*. An IR with an empty ``citations`` list should be
    impossible; if one ever appears here it is a defect worth seeing, not one worth hiding behind a
    filter.
    """
    payload: dict[str, Any] = {
        "id": str(ir.id),
        "domain_profile": ir.domain_profile.value,
        "bearer": ir.bearer,
        "modal": ir.modal,
        "statement": ir.statement,
        #: The class/category restriction lives here, on one IR, rather than fanning out into one
        #: IR per class (ADR-0017 decision 2).
        "condition_text": ir.condition_text,
        "taxonomy_code": ir.taxonomy_code,
        "status": ir.status.value,
        "visible_downstream": ir.is_visible,
        "supersedes_ir_id": str(ir.supersedes_ir_id) if ir.supersedes_ir_id else None,
        "stale_since": ir.stale_since.isoformat() if ir.stale_since else None,
        "locked_by": str(ir.locked_by) if ir.locked_by else None,
        "locked_at": ir.locked_at.isoformat() if ir.locked_at else None,
        "citations": [
            {
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
        "provenance": {
            "llm_provider": ir.llm_provider,
            "llm_model": ir.llm_model,
            "prompt_version": ir.prompt_version,
            "rule_version": ir.rule_version,
            "extraction_run_id": str(ir.extraction_run_id) if ir.extraction_run_id else None,
        },
    }
    if run is not None:
        payload["extraction_run"] = _run_out(run)
    return payload


def _run_out(run: ExtractionRun) -> dict[str, Any]:
    return {
        "id": str(run.id),
        "document_version_id": str(run.document_version_id),
        "domain_profile": run.domain_profile.value,
        "rule_version": run.rule_version,
        "prompt_version": run.prompt_version,
        "llm_provider": run.llm_provider,
        "llm_model": run.llm_model,
        "temperature": run.temperature,
        "status": run.status.value,
        "clauses_seen": run.clauses_seen,
        "irs_written": run.irs_written,
        "rejected_uncited": run.rejected_uncited,
        "started_at": run.started_at.isoformat(),
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "error": run.error,
    }


__all__ = ["router"]
