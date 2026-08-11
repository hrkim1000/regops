"""Amendments re-derive an IR; they never mutate one (ADR-0004 decision 5).

Two steps, and they are deliberately separate stages:

1. **Flagging.** The diff stage already supersedes citations into an amended clause. Here it also
   marks the owning IRs ``stale`` — an obligation whose evidence has moved out from under it, which
   is a different state from "never reviewed" and must stop flowing downstream immediately, without
   waiting for a model to be available.
2. **Re-derivation.** Re-extracting the amended clause in the *new* version produces a **new** IR
   with ``supersedes_ir_id`` pointing at the old one. The old IR is retained, frozen.

Mutating a locked IR in place would silently change the meaning of every control mapping and every
answer that already referenced it, while the audit trail still showed a single approved record. The
cost of the chosen route is that control mappings must be carried forward explicitly — which is
correct, because an amendment that narrows an obligation may invalidate the mapping that satisfied
it, and that is precisely the gap the product exists to find.

**An IR whose clause was removed stays ``stale``.** It is not quietly superseded with no successor:
"this obligation no longer exists" is the highest-impact thing an amendment can say, and it is a
human's call, not a sweep's.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from regops_shared.constants import ChangeKind, Domain, ExtractionRunStatus, IRStatus
from regops_shared.llm import LLMClient, get_llm_client
from regops_shared.models import (
    IR,
    Clause,
    ClauseDiff,
    Document,
    DocumentVersion,
    ExtractionRun,
    IRCitation,
)
from regops_shared.models.base import utcnow

from .agent import extract_clause
from .extract import ExtractionResult, open_run, persist_proposals
from .rules import rule_set_for, triage

log = structlog.get_logger(__name__)


@dataclass(slots=True)
class RederivationResult:
    """What one re-derivation sweep over one version did."""

    document_version_id: uuid.UUID
    stale_seen: int = 0
    superseded: int = 0
    irs_written: int = 0
    #: Stale IRs left stale because their clause was removed, or because re-extraction produced
    #: nothing. Both need an RA, and both are invisible if they are folded into `superseded`.
    unresolved: int = 0
    run_ids: list[uuid.UUID] = field(default_factory=list)


def mark_stale(session: Session, citations: list[IRCitation]) -> int:
    """Flag the IRs behind freshly superseded citations. Flushes; the caller commits.

    ``superseded`` IRs are skipped — they are already frozen evidence, and re-flagging one would
    resurrect a record a later IR has replaced.
    """
    ir_ids = {citation.ir_id for citation in citations}
    if not ir_ids:
        return 0

    now = utcnow()
    stale = 0
    for ir in session.scalars(
        select(IR).where(
            IR.id.in_(ir_ids),
            IR.status.in_((IRStatus.DRAFT, IRStatus.LOCKED)),
        )
    ):
        ir.status = IRStatus.STALE
        ir.stale_since = now
        stale += 1
    session.flush()
    if stale:
        log.info("ir.marked_stale", count=stale)
    return stale


def rederive_version(
    session: Session, version: DocumentVersion, *, client: LLMClient | None = None
) -> RederivationResult:
    """Re-extract every stale IR whose evidence this version amended.

    Scoped to the diffs *into* this version, so a sweep is bounded by one amendment rather than by
    the size of the stale backlog. Commits per IR: a long sweep that dies halfway leaves the IRs it
    already re-derived correctly re-derived.
    """
    result = RederivationResult(document_version_id=version.id)
    document = session.get(Document, version.document_id)
    if document is None:  # pragma: no cover - FK makes this unreachable
        return result

    client = client or get_llm_client()
    runs: dict[Domain, ExtractionRun] = {}

    for ir, citation, diff in _stale_targets(session, version):
        result.stale_seen += 1
        clause = _new_clause(session, diff, version)

        if clause is None:
            # REMOVED, or a diff whose new-side clause no longer resolves. The obligation may have
            # been withdrawn outright — an RA decides, so the IR stays stale and visible as work.
            result.unresolved += 1
            log.info(
                "rederive.no_successor_clause",
                ir=str(ir.id),
                clause_path=citation.clause_path,
                change_kind=diff.change_kind.value,
            )
            continue

        run = runs.get(ir.domain_profile)
        if run is None:
            rules = rule_set_for(ir.domain_profile, version.language)
            run = open_run(session, version, rules=rules, client=client)
            runs[ir.domain_profile] = run
            result.run_ids.append(run.id)

        rules = rule_set_for(ir.domain_profile, version.language)
        verdict = triage(
            clause_kind=clause.kind,
            clause_path=clause.clause_path,
            path_segments=clause.path_segments,
            heading=clause.heading,
            text=clause.text,
            rules=rules,
        )
        if not verdict.needs_agent:
            result.unresolved += 1
            log.info(
                "rederive.clause_no_longer_obligation_bearing",
                ir=str(ir.id),
                clause_path=clause.clause_path,
                reason=verdict.reason.value if verdict.reason else None,
            )
            continue

        agent = extract_clause(
            client,
            rules=rules,
            clause_path=clause.clause_path,
            heading=clause.heading,
            text=clause.text,
            detected_modals=verdict.modals,
        )
        scratch = ExtractionResult(document_version_id=version.id, domain_profile=ir.domain_profile)
        written = persist_proposals(
            session,
            agent,
            run=run,
            rules=rules,
            clause=clause,
            document=document,
            version=version,
            result=scratch,
        )
        if not written:
            result.unresolved += 1
            session.commit()
            continue

        _link_successors(session, ir, run=run, clause=clause, version=version)
        ir.status = IRStatus.SUPERSEDED
        result.superseded += 1
        result.irs_written += written
        session.commit()

    for run in runs.values():
        run.status = ExtractionRunStatus.COMPLETED
        run.completed_at = utcnow()
    session.commit()

    log.info(
        "rederive.done",
        version=str(version.id),
        stale=result.stale_seen,
        superseded=result.superseded,
        irs=result.irs_written,
        unresolved=result.unresolved,
    )
    return result


# --- lookups ---------------------------------------------------------------------------------


def _stale_targets(
    session: Session, version: DocumentVersion
) -> list[tuple[IR, IRCitation, ClauseDiff]]:
    """Stale IRs whose superseding diff landed in this version, one row per IR.

    An IR citing three amended clauses would otherwise be re-derived three times. The first diff is
    enough: re-extraction reads the whole new clause, not the delta.
    """
    rows = session.execute(
        select(IR, IRCitation, ClauseDiff)
        .join(IRCitation, IRCitation.ir_id == IR.id)
        .join(ClauseDiff, ClauseDiff.id == IRCitation.superseded_by_diff_id)
        .where(IR.status == IRStatus.STALE, ClauseDiff.to_version_id == version.id)
        .order_by(IR.created_at)
    ).all()

    seen: set[uuid.UUID] = set()
    out: list[tuple[IR, IRCitation, ClauseDiff]] = []
    for ir, citation, diff in rows:
        if ir.id in seen:
            continue
        seen.add(ir.id)
        out.append((ir, citation, diff))
    return out


def _new_clause(session: Session, diff: ClauseDiff, version: DocumentVersion) -> Clause | None:
    """The amended clause as it stands in the new version, following a renumber.

    ``to_clause_id`` is authoritative because the diff stage resolved the pairing — including the
    renumber and move cases, where the path a reader would look up has changed. Falling back to the
    path keeps this working for a diff whose clause rows were re-parsed underneath it.
    """
    if diff.change_kind is ChangeKind.REMOVED:
        return None
    if diff.to_clause_id is not None:
        clause = session.get(Clause, diff.to_clause_id)
        if clause is not None:
            return clause
    return session.scalar(
        select(Clause).where(
            Clause.document_version_id == version.id, Clause.clause_path == diff.clause_path
        )
    )


def _link_successors(
    session: Session,
    old: IR,
    *,
    run: ExtractionRun,
    clause: Clause,
    version: DocumentVersion,
) -> None:
    """Point the IRs just written at the one they replace.

    All of them: one clause can re-derive into several obligations, and each is a successor to the
    same frozen original. A one-to-one ``supersedes`` chain would have to drop the extras or invent
    a parent, and both lose the link an amendment-impact review needs.
    """
    successors = session.scalars(
        select(IR)
        .join(IRCitation, IRCitation.ir_id == IR.id)
        .where(
            IR.extraction_run_id == run.id,
            IR.supersedes_ir_id.is_(None),
            IRCitation.document_version_id == version.id,
            IRCitation.clause_path == clause.clause_path,
        )
        .distinct()
    ).all()
    for successor in successors:
        successor.supersedes_ir_id = old.id
    session.flush()


__all__ = ["RederivationResult", "mark_stale", "rederive_version"]
