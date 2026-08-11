"""The diff stage: two versions in, ``ClauseDiff`` and ``ChangeEvent`` out.

Its own stage, reached by task name (ADR-0015), so renumber-detection can be re-tuned by re-running
the diff over committed clauses instead of re-deriving them.

**Renumbering is resolved explicitly and never reported as delete + add** (ADR-0002 decision 7).
MFDS 고시 renumber routinely, and a renumbered-but-unchanged 조 emitted as removal plus addition
is two false alerts against the same gate this layer is measured on. Two signals, in strict order:

1. **The authority's own.** 법령 본문조회 publishes ``조문이동이전``/``조문이동이후`` per 조. Where
   the move is *stated*, nothing is inferred and ``similarity`` stays null.
2. **Content similarity**, for everything else — annex rows, 고시 text, and any future source that
   exposes nothing. A match above :data:`RENUMBER_CONFIDENT_RATIO` is accepted; between that and
   :data:`RENUMBER_MATCH_RATIO` it is written *and* queued for RA review, because dropping it would
   lose the change while accepting it silently would assert an identity nobody checked.

Emission stays here rather than becoming a fifth stage: a ``ChangeEvent`` is a pure fan-out over the
claiming cells with no independent input, and a diff committed without its events would under-report
detection coverage.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from difflib import SequenceMatcher

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from regops_shared.constants import (
    RENUMBER_CONFIDENT_RATIO,
    RENUMBER_MATCH_RATIO,
    ChangeKind,
)
from regops_shared.models import (
    ChangeEvent,
    Clause,
    ClauseDiff,
    DocumentCell,
    DocumentVersion,
    IRCitation,
)
from regops_shared.models.base import utcnow

from .extraction.staleness import mark_stale

log = structlog.get_logger(__name__)

#: Above this length, similarity is computed on a prefix. ``SequenceMatcher`` is quadratic, and
#: 별표 1 holds single clauses of 340 KB — comparing them in full would dominate the whole stage for
#: no gain, since two clauses agreeing on their first 2 KB are the same provision.
_SIMILARITY_PREFIX = 2048


@dataclass(slots=True)
class DiffResult:
    """What one diff run produced."""

    to_version_id: uuid.UUID
    from_version_id: uuid.UUID | None = None
    counts: dict[str, int] = field(default_factory=dict)
    change_events: int = 0
    needs_review: int = 0
    citations_superseded: int = 0
    #: IRs moved to ``stale`` because an amendment touched a clause they cite. Re-derivation is a
    #: separate task (ADR-0004 decision 5) — flagging must not wait on a model being reachable.
    irs_marked_stale: int = 0
    baseline: bool = False


def diff_version(session: Session, version: DocumentVersion) -> DiffResult:
    """Diff ``version`` against the previous version of the same document and language."""
    previous = _previous_version(session, version)
    result = DiffResult(to_version_id=version.id)

    if previous is None:
        # The first ingestion of a document is not an amendment. Reporting a whole statute as
        # thousands of additions would drown the signal the coverage gate is measured on.
        result.baseline = True
        log.info("diff.baseline", version=str(version.id))
        return result

    result.from_version_id = previous.id
    old = _clauses(session, previous.id)
    new = _clauses(session, version.id)

    diffs = _build(previous, version, old, new)
    session.add_all(diffs)
    session.flush()

    for diff in diffs:
        result.counts[diff.change_kind.value] = result.counts.get(diff.change_kind.value, 0) + 1
        if diff.needs_review:
            result.needs_review += 1

    result.change_events = _emit(session, version, diffs)
    result.citations_superseded, result.irs_marked_stale = _supersede_citations(
        session, previous, diffs
    )
    session.commit()

    log.info(
        "diff.done",
        version=str(version.id),
        **result.counts,
        change_events=result.change_events,
        needs_review=result.needs_review,
        superseded=result.citations_superseded,
        stale_irs=result.irs_marked_stale,
    )
    return result


# --- pairing -------------------------------------------------------------------------------


def _build(
    previous: DocumentVersion,
    version: DocumentVersion,
    old: list[Clause],
    new: list[Clause],
) -> list[ClauseDiff]:
    """Pair old clauses to new ones, then classify what is left over."""
    by_path_old = {clause.clause_path: clause for clause in old}
    by_path_new = {clause.clause_path: clause for clause in new}

    matched_old: set[uuid.UUID] = set()
    matched_new: set[uuid.UUID] = set()
    diffs: list[ClauseDiff] = []

    def diff(**kwargs: object) -> ClauseDiff:
        return ClauseDiff(from_version_id=previous.id, to_version_id=version.id, **kwargs)  # type: ignore[arg-type]

    # 1. Same path — modified, or genuinely unchanged.
    #
    # **A same-path, same-content clause has not moved, whatever its index.** `ordinal` is a
    # position in a single document-order sequence, so inserting one article near the top shifts
    # every clause below it; reporting that as MOVED emitted 1,209 change events for one 화장품법
    # amendment that had 37 real edits. In a numbered hierarchy the *path is the position* — 제8조
    # always follows 제7조 — so an index shift carries no information a reader could act on, and
    # burying 37 real changes under 1,209 empty ones is the false-alert failure ADR-0002 decision 7
    # exists to prevent. MOVED is reserved for the case where it means something: same clause
    # number, different parent (see `_similarity_renumbers`).
    for path, new_clause in by_path_new.items():
        old_clause = by_path_old.get(path)
        if old_clause is None:
            continue
        matched_old.add(old_clause.id)
        matched_new.add(new_clause.id)
        if old_clause.content_hash != new_clause.content_hash:
            diffs.append(
                diff(
                    clause_path=path,
                    change_kind=ChangeKind.MODIFIED,
                    from_clause_id=old_clause.id,
                    to_clause_id=new_clause.id,
                    match_basis="path",
                )
            )

    leftover_old = [clause for clause in old if clause.id not in matched_old]
    leftover_new = [clause for clause in new if clause.id not in matched_new]

    # 2. The authority's own move signal, before anything is inferred.
    diffs.extend(_authority_renumbers(diff, leftover_old, leftover_new, matched_old, matched_new))

    # 3. Content similarity for whatever is still unpaired.
    diffs.extend(_similarity_renumbers(diff, leftover_old, leftover_new, matched_old, matched_new))

    diffs.extend(
        diff(
            clause_path=clause.clause_path,
            change_kind=ChangeKind.REMOVED,
            from_clause_id=clause.id,
        )
        for clause in leftover_old
        if clause.id not in matched_old
    )
    diffs.extend(
        diff(
            clause_path=clause.clause_path,
            change_kind=ChangeKind.ADDED,
            to_clause_id=clause.id,
        )
        for clause in leftover_new
        if clause.id not in matched_new
    )
    return diffs


def _authority_renumbers(
    diff,
    old: list[Clause],
    new: list[Clause],
    matched_old: set[uuid.UUID],
    matched_new: set[uuid.UUID],
) -> list[ClauseDiff]:
    """Pair on ``조문이동이전`` / ``조문이동이후``, which state the move outright.

    ``similarity`` stays **null** for these: nothing was inferred, and the detection-coverage audit
    needs to tell a stated move apart from a guessed one.
    """
    by_ref = {clause.source_ref: clause for clause in new if clause.source_ref}
    out: list[ClauseDiff] = []

    for old_clause in old:
        target = old_clause.moved_to_ref
        if not target:
            continue
        new_clause = by_ref.get(target)
        if new_clause is None or new_clause.id in matched_new:
            continue
        matched_old.add(old_clause.id)
        matched_new.add(new_clause.id)
        out.append(
            diff(
                clause_path=new_clause.clause_path,
                from_clause_path=old_clause.clause_path,
                change_kind=(
                    ChangeKind.RENUMBERED
                    if _same_but_for_its_number(old_clause, new_clause)
                    else ChangeKind.MODIFIED
                ),
                from_clause_id=old_clause.id,
                to_clause_id=new_clause.id,
                match_basis="authority",
            )
        )
    return out


#: The article number as it appears *inside* ``조문내용``: "제5조(신고) 신고 …".
_LEADING_ARTICLE = re.compile(r"^제\d+조(?:의\d+)?")


def _same_but_for_its_number(old: Clause, new: Clause) -> bool:
    """Is this a pure renumber — the provision unchanged except for the number it now carries?

    ``조문내용`` **embeds the article number**, so a renumbered-but-untouched 제5조 becomes
    "제7조(신고) …" and its ``content_hash`` changes. Comparing hashes directly would classify every
    authority-stated renumber as ``MODIFIED``, which is the false-alert this whole path exists to
    prevent — the alert would say the obligation changed when only its address did.

    So the leading number is stripped before comparing. The heading is deliberately **not**:
    "제5조(신고)" → "제7조(허가)" is a substantive amendment, not a renumber.
    """
    if old.content_hash == new.content_hash:
        return True
    return _LEADING_ARTICLE.sub("", old.text, count=1).strip() == (
        _LEADING_ARTICLE.sub("", new.text, count=1).strip()
    )


def _similarity_renumbers(
    diff,
    old: list[Clause],
    new: list[Clause],
    matched_old: set[uuid.UUID],
    matched_new: set[uuid.UUID],
) -> list[ClauseDiff]:
    """Fallback pairing for sources that publish no move signal.

    Exact content-hash equality is tried first and is free: a clause whose text is byte-identical at
    a different path is a renumber, full stop. Only what survives that goes through
    ``SequenceMatcher``.
    """
    out: list[ClauseDiff] = []
    candidates_old = [clause for clause in old if clause.id not in matched_old]
    candidates_new = [clause for clause in new if clause.id not in matched_new]

    by_hash: dict[str, list[Clause]] = {}
    for clause in candidates_new:
        by_hash.setdefault(clause.content_hash, []).append(clause)

    for old_clause in candidates_old:
        bucket = by_hash.get(old_clause.content_hash)
        while bucket:
            new_clause = bucket.pop(0)
            if new_clause.id in matched_new:
                continue
            matched_old.add(old_clause.id)
            matched_new.add(new_clause.id)
            out.append(
                diff(
                    clause_path=new_clause.clause_path,
                    from_clause_path=old_clause.clause_path,
                    change_kind=_relocation_kind(old_clause, new_clause),
                    from_clause_id=old_clause.id,
                    to_clause_id=new_clause.id,
                    similarity=1.0,
                    match_basis="content_hash",
                )
            )
            break

    remaining_new = [clause for clause in candidates_new if clause.id not in matched_new]
    for old_clause in candidates_old:
        if old_clause.id in matched_old:
            continue
        best, score = _best_match(old_clause, remaining_new)
        if best is None or score < RENUMBER_MATCH_RATIO:
            continue
        matched_old.add(old_clause.id)
        matched_new.add(best.id)
        remaining_new.remove(best)
        out.append(
            diff(
                clause_path=best.clause_path,
                from_clause_path=old_clause.clause_path,
                change_kind=ChangeKind.RENUMBERED,
                from_clause_id=old_clause.id,
                to_clause_id=best.id,
                similarity=score,
                match_basis="similarity",
                # A low-confidence match is a claim about clause identity. It is kept, because
                # dropping it loses the change — and flagged, because nobody has checked it.
                needs_review=score < RENUMBER_CONFIDENT_RATIO,
            )
        )
    return out


def _relocation_kind(old: Clause, new: Clause) -> ChangeKind:
    """``MOVED`` when the clause kept its own number and changed parent; ``RENUMBERED`` otherwise.

    This is the distinction ADR-0002 decision 7 lists both kinds for, and it is the only reading of
    ``MOVED`` that carries information: 제8조 relocated from 제2장 to 제3장 keeps its citation
    number while changing where it sits, which a subscriber to 제2장 needs to know. A clause whose
    own number changed is a renumber and nothing else.
    """
    same_number = old.path_segments[-1:] == new.path_segments[-1:]
    return ChangeKind.MOVED if same_number else ChangeKind.RENUMBERED


def _best_match(clause: Clause, candidates: list[Clause]) -> tuple[Clause | None, float]:
    """Closest candidate by text similarity, restricted to the same clause kind.

    Kind-restriction is cheap and prevents the worst class of false pairing: an annex table row is
    never a renumbered prose article, however similar two short strings look.
    """
    best: Clause | None = None
    score = 0.0
    text = clause.text[:_SIMILARITY_PREFIX]
    for candidate in candidates:
        if candidate.kind is not clause.kind:
            continue
        ratio = SequenceMatcher(
            None, text, candidate.text[:_SIMILARITY_PREFIX], autojunk=False
        ).ratio()
        if ratio > score:
            best, score = candidate, ratio
    return best, score


# --- emission ------------------------------------------------------------------------------


def _emit(session: Session, version: DocumentVersion, diffs: list[ClauseDiff]) -> int:
    """One ``ChangeEvent`` per (diff, claiming cell) — ADR-0003 decision 8.

    Fan-out reaches **every** claiming cell and no others. A document claimed by both gated cells
    produces two events per diff; a single-cell document produces one. Severity stays null: Phase 1
    emits ungraded events and measures whether they are complete and timely.
    """
    cells = list(
        session.scalars(
            select(DocumentCell.cell_id).where(DocumentCell.document_id == version.document_id)
        )
    )
    if not cells:
        log.warning("diff.no_claiming_cell", version=str(version.id))
        return 0

    now = utcnow()
    events = [
        ChangeEvent(
            clause_diff_id=diff.id,
            cell_id=cell_id,
            document_id=version.document_id,
            detected_at=now,
        )
        for diff in diffs
        for cell_id in cells
    ]
    session.add_all(events)
    session.flush()
    return len(events)


def _supersede_citations(
    session: Session, previous: DocumentVersion, diffs: list[ClauseDiff]
) -> tuple[int, int]:
    """Flag citations into amended clauses, and stale the IRs behind them. **Never rewrite one.**

    A citation is pinned to an immutable version (ADR-0002 decision 4). Repointing it at the new
    version would silently change the evidence behind an obligation an RA already locked, while the
    audit trail still showed one approved record. So the row is flagged, the original stays
    resolvable, and re-verification is queued — which is the product feature that makes "missed
    amendment impact analyses = 0" measurable, not a maintenance chore.

    Flagging the citation is not enough on its own: the *IR* is what downstream reads, and an IR
    still marked ``locked`` over evidence that has moved would keep flowing into answers and impact
    grades. So it moves to ``stale`` here, synchronously, in the same transaction — re-derivation is
    a separate task (ADR-0004 decision 5) precisely so that stopping the flow never waits on a model
    being reachable.

    Returns ``(citations_superseded, irs_marked_stale)``.
    """
    touched = {
        diff.from_clause_path or diff.clause_path: diff
        for diff in diffs
        if diff.change_kind is not ChangeKind.ADDED
    }
    if not touched:
        return 0, 0

    citations = list(
        session.scalars(
            select(IRCitation).where(
                IRCitation.document_version_id == previous.id,
                IRCitation.clause_path.in_(list(touched)),
                IRCitation.superseded_at.is_(None),
            )
        )
    )

    now = utcnow()
    for citation in citations:
        citation.superseded_at = now
        citation.superseded_by_diff_id = touched[citation.clause_path].id
    session.flush()
    return len(citations), mark_stale(session, citations)


# --- lookups -------------------------------------------------------------------------------


def _previous_version(session: Session, version: DocumentVersion) -> DocumentVersion | None:
    """The version this one amends: same document, same language, most recent before it.

    Ordered by ``retrieved_at`` rather than ``effective_date`` on purpose — a 시행예정 version is
    fetched later but takes effect years hence, and ordering by effective date would diff it against
    a future sibling rather than against the text it actually amends.
    """
    return session.scalar(
        select(DocumentVersion)
        .where(
            DocumentVersion.document_id == version.document_id,
            DocumentVersion.language == version.language,
            DocumentVersion.id != version.id,
            DocumentVersion.retrieved_at <= version.retrieved_at,
            DocumentVersion.parser_version.is_not(None),
        )
        .order_by(DocumentVersion.retrieved_at.desc(), DocumentVersion.created_at.desc())
        .limit(1)
    )


def _clauses(session: Session, version_id: uuid.UUID) -> list[Clause]:
    return list(
        session.scalars(
            select(Clause).where(Clause.document_version_id == version_id).order_by(Clause.ordinal)
        )
    )


__all__ = ["DiffResult", "diff_version"]
