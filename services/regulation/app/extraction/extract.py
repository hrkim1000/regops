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

That clearing is why a *concurrent* run is destructive rather than merely wasteful, and why this
module refuses one itself instead of trusting the API's 409 to be the only door: a task redelivered
by the broker never passes through the API at all.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import structlog
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from regops_shared.constants import (
    EXTRACTION_COMMIT_EVERY,
    EXTRACTION_RESUME_CHAIN_MAX,
    EXTRACTION_TEMPERATURE,
    ClassificationKind,
    Domain,
    ExclusionReason,
    ExtractionRunStatus,
    IRStatus,
    extraction_run_is_live,
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
    #: Clauses this run took from an interrupted predecessor instead of re-examining.
    resumed: int = 0
    exclusion_reasons: dict[str, int] = field(default_factory=dict)
    #: Set when a complete extraction at this fingerprint already existed and ``force`` was not
    #: given. **Not an error** — nothing was wrong and nothing was done, so ``ok`` stays true and
    #: the caller reports a no-op rather than a failure.
    already_complete: bool = False
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
    force: bool = False,
) -> ExtractionResult:
    """Extract one version under one domain profile. Commits incrementally.

    ``force`` is what separates a deliberate redo from a duplicate message (ADR-0022 decision 4).
    Without it, a version already **fully** extracted at the current fingerprint is a no-op; with
    it, the redo proceeds exactly as it always did.
    """
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

    live = _live_run(session, version, domain=domain)
    if live is not None:
        # **A redelivered task is not a second request.** The API refuses a concurrent extraction
        # with 409, but a duplicate does not have to come through the API: Redis redelivers any
        # task still running at the broker's visibility timeout, and the worker runs `-c 2`, so the
        # copy lands in the sibling child beside the original. Observed 2026-08-27 on 의료기기법 —
        # one POST at 01:24, the same task id received again at 02:25, and the copy's
        # `_clear_previous_drafts` destroyed 89 drafts the live run had already committed.
        #
        # So the refusal belongs here, at the one point every path to an extraction passes through,
        # rather than only at the door the duplicate never used. Nothing is written and no run is
        # opened — the live one keeps its drafts and its clause ledger.
        result.run_id = live.id
        result.error = (
            f"extraction {live.id} is already live for this version and profile; refused rather "
            f"than clearing its drafts"
        )
        log.warning(
            "extract.already_live",
            version=str(version.id),
            domain=domain.value,
            live_run=str(live.id),
            live_clauses=live.clauses_seen,
        )
        return result

    rules = rule_set_for(domain, version.language)
    client = client or get_llm_client()

    if not force:
        settled = _completed_at_fingerprint(
            session, version, domain=domain, rules=rules, client=client
        )
        if settled is not None:
            # **A redelivered message and a deliberate redo are the same two arguments.** Killing a
            # worker returns whatever it held to the queue, and the copy arrives looking exactly
            # like a fresh request — so the only thing that can tell them apart is an intent the
            # original dispatch carried. `force` is that intent.
            #
            # Refusing here matters because the next statements are destructive:
            # `_clear_previous_drafts` deletes the drafts of every run outside the resume chain, and
            # a completed run is never in one (`_resumable_run` returns None for it, deliberately,
            # so that a *real* redo is not silently a no-op). On 2026-09-08 that cost five hours of
            # GPU over 43 versions that were already done, and again on 09-09 when Docker was killed
            # mid-batch: 24341#별표2 lost 361 committed IRs to a message nobody re-sent.
            result.run_id = settled.id
            result.already_complete = True
            log.info(
                "extract.already_complete",
                version=str(version.id),
                domain=domain.value,
                run=str(settled.id),
                rule_version=rules.rule_version,
                prompt_version=rules.prompt_version,
                llm_model=client.model,
            )
            return result

    # **A crash should cost minutes, not the whole model budget.** `_checkpoint` has always
    # committed every `EXTRACTION_COMMIT_EVERY` clauses, but nothing read those commits back, so a
    # run that died at clause 600 of 729 started again at clause 1 — which is what the Postgres
    # crash of 2026-08-27 actually cost: two hours of `gemma3:4b`, not the ninety seconds the
    # database was down.
    resume_from = _resumable_run(session, version, domain=domain, rules=rules, client=client)
    resume_chain = _resume_chain(session, resume_from)
    run = open_run(session, version, rules=rules, client=client, resumed_from=resume_from)
    result.run_id = run.id

    # Spares the predecessor's drafts and clears every other draft, so a clause is either adopted
    # whole or re-examined with nothing of its own left behind. There is no third state where a
    # cleared clause keeps a classification saying it was done.
    _clear_previous_drafts(session, version, domain=domain, keep_runs=resume_chain)
    done = _clauses_done_by(session, version, runs=resume_chain)
    if done:
        bound_resume = log.bind(version=str(version.id), domain=domain.value)
        bound_resume.info(
            "extract.resuming",
            from_run=str(resume_from.id) if resume_from else None,
            chain=[str(r.id) for r in resume_chain],
            clauses_adopted=len(done),
        )

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
                done=done,
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
        resumed=result.resumed,
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
    done: frozenset[uuid.UUID] = frozenset(),
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

    # Adopted from the interrupted run — its classification and its IRs are already committed.
    #
    # **After `triage`, never before.** A clause's exclusion reason descends to its children
    # (`INHERITABLE_REASONS`), so the trail has to be walked for every clause in document order or a
    # later one inherits from a gap. Triage is deterministic and free; the LLM call is what this
    # skips.
    if clause.id in done:
        result.resumed += 1
        return

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


def _live_run(
    session: Session, version: DocumentVersion, *, domain: Domain
) -> ExtractionRun | None:
    """The run still working this ``(version, domain)`` — not merely one still saying ``running``.

    Same rule as the API's concurrency guard, from the same shared helper, so the two cannot drift
    into disagreeing about what "live" means. A row with no pulse is *not* live: a worker killed
    mid-corpus would otherwise make the version permanently unextractable, and closing that row is
    the caller's job, not this predicate's.
    """
    candidates = session.scalars(
        select(ExtractionRun).where(
            ExtractionRun.document_version_id == version.id,
            ExtractionRun.domain_profile == domain,
            ExtractionRun.status == ExtractionRunStatus.RUNNING,
        )
    )
    return next(
        (run for run in candidates if extraction_run_is_live(run.status.value, run.heartbeat_at)),
        None,
    )


def _completed_at_fingerprint(
    session: Session,
    version: DocumentVersion,
    *,
    domain: Domain,
    rules: RuleSet,
    client: LLMClient,
) -> ExtractionRun | None:
    """A finished extraction that leaves nothing for this one to do, or ``None``.

    Two conditions, and both are needed (ADR-0022 decision 4).

    - **A ``COMPLETED`` run at an identical fingerprint.** Identical because
      ``rule_version``/``prompt_version``/``llm_provider``/``llm_model`` are the promise stamped on
      every IR (ADR-0017 decision 1): a rule-set bump makes re-extraction *the point*, not a
      duplicate, so the guard must stand aside for it.
    - **Every clause classified *by that run or its resume chain*.** The run row says the work
      finished; the clause ledger says what it covered. Trusting only the row would skip a version
      whose run was marked complete over clauses it never reached, and an unexamined clause reads
      as an obligation-free one — exactly the confusion ADR-0004 decision 6 exists to prevent.

    **The attribution is the whole point of the second test, and leaving it out was a bug.** A bare
    "no unclassified clause" count passed on 2026-09-09 for a version that was 475 of 542 done:
    ``clause_classifications`` is unique per ``(clause, domain)``, so a later run *overwrites* rows
    rather than adding to them, and a failed re-run had taken over 475 of the completed run's rows
    while its 67 leftovers made the ledger add up to full coverage. The clauses were classified;
    they were classified by a run whose IRs no longer existed, and 218 obligation-bearing clauses
    had 206 IRs between them. Counting rows without asking who wrote them measures the wrong thing.

    The chain rather than the single run because a resumed completion is a legitimate one: run B
    adopts A's clauses and A keeps its rows, so their union is what B actually covers.

    Deliberately *not* a heartbeat question. ``_live_run`` answers "is someone working on this now";
    this answers "is there anything left to do", and a version can be settled for weeks.
    """
    settled = session.scalars(
        select(ExtractionRun)
        .where(
            ExtractionRun.document_version_id == version.id,
            ExtractionRun.domain_profile == domain,
            ExtractionRun.status == ExtractionRunStatus.COMPLETED,
            ExtractionRun.rule_version == rules.rule_version,
            ExtractionRun.prompt_version == rules.prompt_version,
            ExtractionRun.llm_provider == client.provider,
            ExtractionRun.llm_model == client.model,
        )
        .order_by(ExtractionRun.started_at.desc())
        .limit(1)
    ).first()
    if settled is None:
        return None

    covered = [run.id for run in _resume_chain(session, settled)]
    missing = session.scalar(
        select(func.count())
        .select_from(Clause)
        .outerjoin(
            ClauseClassification,
            (ClauseClassification.clause_id == Clause.id)
            & (ClauseClassification.domain_profile == domain)
            & (ClauseClassification.extraction_run_id.in_(covered)),
        )
        .where(
            Clause.document_version_id == version.id,
            ClauseClassification.id.is_(None),
        )
    )
    return settled if not missing else None


def _resumable_run(
    session: Session,
    version: DocumentVersion,
    *,
    domain: Domain,
    rules: RuleSet,
    client: LLMClient,
) -> ExtractionRun | None:
    """The interrupted run this one may continue, or ``None`` to start clean.

    **The most recent run, if it has stopped and is not finished, at an identical fingerprint.**

    - *Most recent* because an older one's drafts have since been cleared by whatever ran after it;
      adopting its clauses would keep classifications saying "examined" over IRs that no longer
      exist, which reads as an obligation-free article rather than as missing work.
    - *Stopped, not finished* because a completed run means the work is done — a re-run after one is
      a deliberate redo, and silently adopting its output would make the redo a no-op.
    - *Identical fingerprint* because ``rule_version``/``prompt_version``/``llm_model`` are the
      promise stamped on every IR (ADR-0017 decision 1). Adopting clauses across a version change
      would produce one run's worth of rows that two different rule sets wrote.

    **"Stopped" is a pulse question, not a status question, and that distinction cost 945 IRs.**
    This asked for ``FAILED`` when it was written, which is the state a *swept* crash leaves. A
    crash that nothing has swept yet leaves ``RUNNING`` with a dead heartbeat — and nothing sweeps
    on the dispatch path, because ``_fail_orphaned_runs`` fires on ``worker_ready`` and the API's
    guard only runs when someone uses the API. So on 2026-08-28 a run killed at 2,625 of 12,179
    clauses sat at ``RUNNING``, and re-dispatching it would have started from clause 1 and cleared
    the 945 drafts it had already committed — the exact loss resuming exists to prevent, reachable
    because resumption depended on a sweep having happened first.

    Reading the heartbeat instead makes the answer self-contained. It is the same threshold
    ``_live_run`` uses, so the two cannot disagree about whether a run is still working; a run that
    still holds a pulse is a live peer, and ``extract_version`` refuses beside it rather than racing
    it. Checking it here too is belt-and-braces: correctness must not rest on the order in which
    that function and this one happen to be called.
    """
    candidate = session.scalars(
        select(ExtractionRun)
        .where(
            ExtractionRun.document_version_id == version.id,
            ExtractionRun.domain_profile == domain,
        )
        .order_by(ExtractionRun.started_at.desc())
        .limit(1)
    ).first()
    if candidate is None or candidate.status is ExtractionRunStatus.COMPLETED:
        return None
    if extraction_run_is_live(candidate.status.value, candidate.heartbeat_at):
        return None
    same_fingerprint = (
        candidate.rule_version == rules.rule_version
        and candidate.prompt_version == rules.prompt_version
        and candidate.llm_provider == client.provider
        and candidate.llm_model == client.model
    )
    return candidate if same_fingerprint else None


def _resume_chain(session: Session, run: ExtractionRun | None) -> list[ExtractionRun]:
    """The run being resumed and everything it, in turn, resumed. Newest first; empty for ``None``.

    **A resuming run keeps its predecessor's drafts**, so the chain is a list of runs whose work is
    all still live — not a history where only the last entry matters. Reading only the head is what
    deleted 938 IRs on 2026-09-04: the third run over 21 U.S.C. chapter 9 adopted the second's 1,400
    clauses and cleared the first's drafts as though something had already superseded them.

    Bounded by `EXTRACTION_RESUME_CHAIN_MAX` and by a seen-set. The column is a self-reference, and
    a cycle in it would otherwise hang the extractor before it read a single clause — cheap
    insurance against a row nobody expected.
    """
    chain: list[ExtractionRun] = []
    seen: set[uuid.UUID] = set()
    current = run
    while current is not None and len(chain) < EXTRACTION_RESUME_CHAIN_MAX:
        if current.id in seen:
            log.warning("extract.resume_chain_cycle", run=str(current.id))
            break
        seen.add(current.id)
        chain.append(current)
        current = (
            session.get(ExtractionRun, current.resumed_from_id) if current.resumed_from_id else None
        )
    if current is not None:
        # Truncated rather than silently partial: the caller is about to clear the drafts of every
        # run it did *not* adopt, so a chain that ran off the end is a reason to say so loudly.
        log.warning(
            "extract.resume_chain_truncated", head=str(run.id) if run else None, kept=len(chain)
        )
    return chain


def _clauses_done_by(
    session: Session, version: DocumentVersion, *, runs: list[ExtractionRun]
) -> frozenset[uuid.UUID]:
    """Clauses the resume chain finished — safe to adopt rather than re-examine.

    A committed classification is the marker, and it is sound because of the write order in
    :func:`_process`: the IRs go in first and the classification last, both inside the transaction
    that ``_checkpoint`` commits. So a classification that survived the crash has its IRs beside it,
    and a lost batch lost both together. There is no committed state where a clause claims to be
    classified while its obligations are missing.
    """
    if not runs:
        return frozenset()
    rows = session.scalars(
        select(ClauseClassification.clause_id)
        .join(Clause, Clause.id == ClauseClassification.clause_id)
        .where(
            Clause.document_version_id == version.id,
            ClauseClassification.extraction_run_id.in_([r.id for r in runs]),
        )
    )
    return frozenset(rows)


def open_run(
    session: Session,
    version: DocumentVersion,
    *,
    rules: RuleSet,
    client: LLMClient,
    resumed_from: ExtractionRun | None = None,
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
        # Recorded, not inferred. See `_resume_chain` for what it costs to guess this.
        resumed_from_id=resumed_from.id if resumed_from else None,
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


def _clear_previous_drafts(
    session: Session,
    version: DocumentVersion,
    *,
    domain: Domain,
    keep_runs: list[ExtractionRun] | None = None,
) -> None:
    """Drop unreviewed proposals from an earlier run of this version and profile.

    Only ``draft``. A ``locked`` IR carries a human signature, a ``stale`` one is waiting for
    re-derivation, and a ``superseded`` one is frozen evidence for citations that already exist —
    re-running an extractor is not a reason to destroy any of the three.

    ``ir_citations`` cascades from ``irs``, so the deferred uncited-IR trigger sees the IR gone and
    stays quiet.
    """
    conditions = [
        IRCitation.document_version_id == version.id,
        IR.domain_profile == domain,
        IR.status == IRStatus.DRAFT,
    ]
    if keep_runs:
        # Spared by **run**, not by citation path. An IR can cite a second clause for a condition
        # that lives elsewhere, so a path-based exclusion would delete an IR the resumed run wrote
        # merely because one of its citations points at a clause about to be re-examined.
        #
        # The whole chain is spared, not just its head: every run in it kept the one before, so all
        # of their drafts are live work rather than superseded leftovers.
        kept = [r.id for r in keep_runs]
        conditions.append(or_(IR.extraction_run_id.is_(None), IR.extraction_run_id.notin_(kept)))
    doomed = (
        select(IR.id)
        .join(IRCitation, IRCitation.ir_id == IR.id)
        .where(*conditions)
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
