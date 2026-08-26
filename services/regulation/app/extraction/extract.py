"""The extraction stage: a parsed version in, draft IRs and a full classification ledger out.

Runs **once per (version, claiming domain)**. A document claimed by both gated cells is extracted
twice — once under the SaMD rule set, once under the Cosmetic one — because a clause bearing a duty
under one taxonomy may bear none under the other, and forcing the two readings to share a row would
make the domain branch a fiction (ADR-0004 decision 3).

Three invariants are enforced here rather than hoped for:

- **Every clause gets a classification** (decision 6). Obligation-bearing, or excluded with a
  reason. There is no unclassified remainder, which is what makes coverage provable: *this clause
  was examined and deliberately yielded nothing* is a different claim from silence.
- **An IR without a citation is rejected, not stored** (decision 2). A proposal whose ``cites``
  resolve to no clause in this version is counted on the run and discarded. The database backs this
  up with a deferred constraint trigger, so the invariant does not depend on this file being right.
- **Extraction produces ``draft``** (decision 4). Nothing here writes ``locked``; that is a human
  action through the API, and it is the only thing that makes an IR visible downstream.

Idempotent per ``(version, domain)``: a re-run deletes the *draft* IRs a previous run left and
writes again. It never touches a ``locked``, ``stale`` or ``superseded`` IR — those are evidence a
human acted on, and re-running an extractor is not a reason to discard that. Human-authored
classifications survive a re-run for the same reason.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import structlog
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from regops_shared.constants import (
    EXTRACTION_COMMIT_EVERY,
    EXTRACTION_TEMPERATURE,
    ClassificationKind,
    Domain,
    ExclusionReason,
    ExtractionRunStatus,
    IRStatus,
)
from regops_shared.llm import LLMClient, get_llm_client
from regops_shared.models import (
    IR,
    Cell,
    Clause,
    ClauseClassification,
    Document,
    DocumentCell,
    DocumentVersion,
    ExtractionRun,
    IRCitation,
)
from regops_shared.models.base import utcnow

from .agent import AgentResult, Proposal, extract_clause
from .rules import INHERITABLE_REASONS, RuleSet, Triage, rule_set_for, triage

log = structlog.get_logger(__name__)

#: Task name the re-derivation stage registers. Dispatch is by name only — stages never import each
#: other's graph, even inside one service (ADR-0015).
REDERIVE_TASK = "regulation.rederive_stale_irs"


@dataclass(slots=True)
class ExtractionResult:
    """What one run over one version, under one domain profile, produced."""

    document_version_id: uuid.UUID
    domain_profile: Domain
    run_id: uuid.UUID | None = None
    clauses_seen: int = 0
    obligation_bearing: int = 0
    excluded: int = 0
    irs_written: int = 0
    rejected_uncited: int = 0
    exclusion_reasons: dict[str, int] = field(default_factory=dict)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def extract_version(
    session: Session,
    version: DocumentVersion,
    *,
    domain: Domain,
    client: LLMClient | None = None,
) -> ExtractionResult:
    """Extract one version under one domain profile. Commits incrementally."""
    result = ExtractionResult(document_version_id=version.id, domain_profile=domain)

    document = session.get(Document, version.document_id)
    if document is None:  # pragma: no cover - FK makes this unreachable
        result.error = "version has no document"
        return result

    clauses = list(
        session.scalars(
            select(Clause).where(Clause.document_version_id == version.id).order_by(Clause.ordinal)
        )
    )
    if not clauses:
        # A parsed version always has clauses (`parse._fail_closed` removes one that does not), so
        # this is a feed or an unparsed version. Neither is an extraction failure, and creating an
        # empty run would report a domain as covered when nothing was examined.
        log.info("extract.no_clauses", version=str(version.id), domain=domain.value)
        return result

    rules = rule_set_for(domain, version.language)
    client = client or get_llm_client()
    run = open_run(session, version, rules=rules, client=client)
    result.run_id = run.id

    _clear_previous_drafts(session, version, domain=domain)

    bound = log.bind(version=str(version.id), domain=domain.value, run=str(run.id))
    #: Paths whose role a child inherits, accumulated as we go. Clauses arrive in document order, so
    #: a provision is always classified before anything beneath it — no second pass and no query.
    roles = _RoleTrail()
    try:
        for index, clause in enumerate(clauses, start=1):
            _process(
                session,
                clause,
                run=run,
                rules=rules,
                client=client,
                document=document,
                version=version,
                result=result,
                roles=roles,
            )
            if index % EXTRACTION_COMMIT_EVERY == 0:
                _checkpoint(session, run, result)
    except Exception as exc:
        # A run that dies mid-corpus must be *visibly* incomplete. Leaving it `running` forever
        # would read as "still working" and the partial IRs would look like the whole extraction.
        run.status = ExtractionRunStatus.FAILED
        run.error = describe_exception(exc)
        run.completed_at = utcnow()
        _checkpoint(session, run, result)
        result.error = run.error
        bound.error("extract.failed", error=run.error)
        raise

    run.status = ExtractionRunStatus.COMPLETED
    run.completed_at = utcnow()
    _checkpoint(session, run, result)

    bound.info(
        "extract.done",
        clauses=result.clauses_seen,
        obligation_bearing=result.obligation_bearing,
        excluded=result.excluded,
        irs=result.irs_written,
        rejected=result.rejected_uncited,
    )
    return result


def domains_for(session: Session, document_id: uuid.UUID) -> list[Domain]:
    """The domains whose rule sets claim this document, via its cells.

    Deduplicated: a document claimed by ``mfds_samd`` and (hypothetically) ``fda_samd`` is one SaMD
    reading, not two. The *cell* is the unit of coverage; the *domain* is the unit of extraction.
    """
    rows = session.scalars(
        select(Cell.domain)
        .join(DocumentCell, DocumentCell.cell_id == Cell.id)
        .where(DocumentCell.document_id == document_id)
    ).all()
    return sorted(set(rows), key=lambda d: d.value)


# --- one clause ------------------------------------------------------------------------------


def describe_exception(exc: BaseException) -> str:
    """A failure reason that survives an exception carrying no message.

    ``run.error`` used to be ``str(exc)``, which is correct for anything raised with a sentence and
    **empty for the transport errors that actually end a run**: ``httpx.ReadTimeout`` and
    ``ConnectError`` are raised with an empty message, so ``str()`` on them is ``""``. A run over
    the FD&C Act died on one after 291 of 12,179 clauses and recorded its reason as the empty
    string — the column exists so a failure is legible without reading a worker log, and it said
    nothing at all.

    So the type leads and the message follows where there is one. ``httpx.ReadTimeout`` is a
    complete answer on its own; ``ValueError`` is not, and keeps its text.
    """
    name = type(exc).__name__
    module = type(exc).__module__
    qualified = name if module in ("builtins", None) else f"{module}.{name}"
    detail = str(exc).strip()
    return (f"{qualified}: {detail}" if detail else qualified)[:2000]


class _RoleTrail:
    """Which provisions carry a role their sub-clauses keep, by path prefix.

    A definitions article states its heading once and its 호 / paragraphs say nothing about being
    definitions — they simply define terms. Reading each clause alone therefore sends them to the
    agent, which is how 21 CFR 700.3(g) produced an IR asserting an obligation a definition cannot
    impose.

    Prefix matching on ``clause_path`` rather than ``parent_clause_id``: the role descends the whole
    subtree, not one level, and the path already encodes ancestry. The ``/`` is required in the
    comparison so ``제2조`` does not claim ``제20조`` — the same over-match that
    :func:`~app.extraction.rules._role_of` guards against in headings.
    """

    __slots__ = ("_prefixes",)

    def __init__(self) -> None:
        self._prefixes: dict[str, ExclusionReason] = {}

    def role_above(self, clause_path: str) -> ExclusionReason | None:
        for prefix, reason in self._prefixes.items():
            if clause_path.startswith(f"{prefix}/"):
                return reason
        return None

    def record(self, clause_path: str, reason: ExclusionReason | None) -> None:
        if reason is not None and reason in INHERITABLE_REASONS:
            self._prefixes[clause_path] = reason


def _process(
    session: Session,
    clause: Clause,
    *,
    run: ExtractionRun,
    rules: RuleSet,
    client: LLMClient,
    document: Document,
    version: DocumentVersion,
    result: ExtractionResult,
    roles: _RoleTrail,
) -> None:
    """Classify one clause and, if it bears obligations, write the IRs it yields."""
    result.clauses_seen += 1

    verdict = triage(
        clause_kind=clause.kind,
        clause_path=clause.clause_path,
        path_segments=clause.path_segments,
        heading=clause.heading,
        text=clause.text,
        rules=rules,
        inherited=roles.role_above(clause.clause_path),
    )
    roles.record(clause.clause_path, verdict.reason)

    if not verdict.needs_agent:
        _classify(session, clause, run=run, rules=rules, verdict=verdict, result=result)
        return

    agent = extract_clause(
        client,
        rules=rules,
        clause_path=clause.clause_path,
        heading=clause.heading,
        text=clause.text,
        detected_modals=verdict.modals,
    )
    if agent.discarded:
        log.info("extract.discarded", clause_path=clause.clause_path, reasons=agent.discarded[:5])

    rejected_before = result.rejected_uncited
    written = persist_proposals(
        session,
        agent,
        run=run,
        rules=rules,
        clause=clause,
        document=document,
        version=version,
        result=result,
    )

    if written:
        _classify(session, clause, run=run, rules=rules, verdict=verdict, result=result)
        return

    # The clause carried an inventory modal but produced no storable IR. That is still an
    # *examined* clause, and the reason has to distinguish "the agent answered nothing usable" from
    # "the agent read it and found no duty" — the first is a prompt regression and the second is a
    # legitimate verdict, and a shared reason would hide the first inside the second.
    #
    # The rejection test is a **delta**, not `result.rejected_uncited`. That counter is run-wide, so
    # reading it directly would label every later empty clause `unparseable` once any one clause had
    # a rejection — turning one bad proposal into a run-wide false regression signal.
    unusable = (
        agent.unparseable or bool(agent.discarded) or result.rejected_uncited > rejected_before
    )
    reason = ExclusionReason.UNPARSEABLE if unusable else ExclusionReason.NO_OBLIGATION
    _classify(
        session,
        clause,
        run=run,
        rules=rules,
        verdict=Triage(ClassificationKind.EXCLUDED, reason, note=_note(agent)),
        result=result,
    )


def persist_proposals(
    session: Session,
    agent: AgentResult,
    *,
    run: ExtractionRun,
    rules: RuleSet,
    clause: Clause,
    document: Document,
    version: DocumentVersion,
    result: ExtractionResult,
) -> int:
    """Write the IRs one clause yielded. Returns how many reached a row."""
    written = 0
    for proposal in agent.proposals:
        citations = _resolve(session, proposal, clause=clause, version=version)
        if not citations:
            # ADR-0004 decision 2: rejected, not stored with a null citation. An uncited IR would
            # launder an unsourced claim into gap analysis, where it would look like a finding.
            result.rejected_uncited += 1
            run.rejected_uncited += 1
            log.warning(
                "extract.rejected_uncited",
                clause_path=clause.clause_path,
                cites=list(proposal.cites),
            )
            continue

        ir = IR(
            domain_profile=rules.domain,
            bearer=proposal.bearer,
            modal=proposal.modal,
            statement=proposal.statement,
            condition_text=proposal.condition_text,
            taxonomy_code=proposal.taxonomy_code,
            status=IRStatus.DRAFT,
            extraction_run_id=run.id,
            llm_provider=agent.provider,
            llm_model=agent.model,
            prompt_version=rules.prompt_version,
            rule_version=rules.rule_version,
        )
        session.add(ir)
        session.flush()

        for cited in citations:
            session.add(
                IRCitation(
                    ir_id=ir.id,
                    document_id=document.id,
                    document_version_id=version.id,
                    clause_path=cited.clause_path,
                    # The clause's own date where it states one, else the version's (ADR-0003
                    # decision 5). Null stays null — a computed date never enters the tuple.
                    effective_date=cited.effective_date or version.effective_date,
                )
            )
        session.flush()

        written += 1
        result.irs_written += 1
        run.irs_written += 1
    return written


def _resolve(
    session: Session, proposal: Proposal, *, clause: Clause, version: DocumentVersion
) -> list[Clause]:
    """Turn the model's ``cites`` into clauses of **this version**. Unresolvable paths are dropped.

    The clause under examination is not force-added. If the model named only paths that do not
    exist, it has asserted the obligation lives somewhere we cannot verify, and substituting the
    source clause would manufacture evidence for a claim it did not make.
    """
    resolved: dict[str, Clause] = {}
    for path in proposal.cites:
        if path == clause.clause_path:
            resolved[path] = clause
            continue
        found = session.scalar(
            select(Clause).where(
                Clause.document_version_id == version.id, Clause.clause_path == path
            )
        )
        if found is not None:
            resolved[path] = found
    return list(resolved.values())


def _classify(
    session: Session,
    clause: Clause,
    *,
    run: ExtractionRun,
    rules: RuleSet,
    verdict: Triage,
    result: ExtractionResult,
) -> None:
    """Record that this clause was examined. Upsert, preserving a human's override.

    ``classified_by`` non-null means an ``ra`` disagreed with the agent and said so. A re-run of the
    extractor is not new evidence about that judgement, so it leaves the row alone.
    """
    existing = session.scalar(
        select(ClauseClassification).where(
            ClauseClassification.clause_id == clause.id,
            ClauseClassification.domain_profile == rules.domain,
        )
    )
    if existing is not None and existing.classified_by is not None:
        _count(result, existing.kind, existing.exclusion_reason)
        return

    row = existing or ClauseClassification(clause_id=clause.id, domain_profile=rules.domain)
    row.kind = verdict.kind
    row.exclusion_reason = verdict.reason
    row.exclusion_note = verdict.note
    row.extraction_run_id = run.id
    row.classified_at = utcnow()
    if existing is None:
        session.add(row)

    _count(result, verdict.kind, verdict.reason)


def _count(
    result: ExtractionResult, kind: ClassificationKind, reason: ExclusionReason | None
) -> None:
    if kind is ClassificationKind.OBLIGATION_BEARING:
        result.obligation_bearing += 1
        return
    result.excluded += 1
    if reason is not None:
        key = reason.value
        result.exclusion_reasons[key] = result.exclusion_reasons.get(key, 0) + 1


def _note(agent: AgentResult) -> str | None:
    if agent.unparseable:
        return "agent returned nothing parseable"
    return "; ".join(agent.discarded)[:500] or None


# --- run bookkeeping -------------------------------------------------------------------------


def open_run(
    session: Session, version: DocumentVersion, *, rules: RuleSet, client: LLMClient
) -> ExtractionRun:
    run = ExtractionRun(
        document_version_id=version.id,
        domain_profile=rules.domain,
        rule_version=rules.rule_version,
        prompt_version=rules.prompt_version,
        llm_provider=client.provider,
        llm_model=client.model,
        temperature=EXTRACTION_TEMPERATURE,
        status=ExtractionRunStatus.RUNNING,
        started_at=utcnow(),
        # A run is live from the moment it opens, not from its first checkpoint — otherwise the
        # first `EXTRACTION_COMMIT_EVERY` clauses would read as a dead run and the concurrency
        # guard would let a second worker in over the same clauses.
        heartbeat_at=utcnow(),
    )
    session.add(run)
    session.commit()
    return run


def _checkpoint(session: Session, run: ExtractionRun, result: ExtractionResult) -> None:
    """Commit progress so a worker restart resumes rather than restarts.

    The heartbeat rides along on the write that was happening anyway. It is what lets a reader tell
    a working run from a row that merely still says ``running`` — ``started_at`` never moves, so on
    its own it makes a run killed after one clause look like one still going three hours in
    (``extraction_run_is_live``).
    """
    run.clauses_seen = result.clauses_seen
    run.heartbeat_at = utcnow()
    session.commit()


def _clear_previous_drafts(session: Session, version: DocumentVersion, *, domain: Domain) -> None:
    """Drop unreviewed proposals from an earlier run of this version and profile.

    Only ``draft``. A ``locked`` IR carries a human signature, a ``stale`` one is waiting for
    re-derivation, and a ``superseded`` one is frozen evidence for citations that already exist —
    re-running an extractor is not a reason to destroy any of the three.

    ``ir_citations`` cascades from ``irs``, so the deferred uncited-IR trigger sees the IR gone and
    stays quiet.
    """
    doomed = (
        select(IR.id)
        .join(IRCitation, IRCitation.ir_id == IR.id)
        .where(
            IRCitation.document_version_id == version.id,
            IR.domain_profile == domain,
            IR.status == IRStatus.DRAFT,
        )
        .distinct()
        .scalar_subquery()
    )
    removed = session.execute(delete(IR).where(IR.id.in_(doomed))).rowcount or 0
    session.commit()
    if removed:
        log.info(
            "extract.cleared_drafts",
            version=str(version.id),
            domain=domain.value,
            drafts=removed,
        )


__all__ = [
    "REDERIVE_TASK",
    "ExtractionResult",
    "domains_for",
    "extract_version",
    "open_run",
    "persist_proposals",
]
