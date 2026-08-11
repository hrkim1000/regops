"""Flagging answers whose evidence has moved — ADR-0002 decision 4, ADR-0006 decision 10.

An answer citation and an IR citation share a shape and nothing else:

- IR citation → the clause is amended → the IR goes **stale** and is re-derived
- answer citation → the clause is amended → the answer goes **superseded** and is re-verified

So the two live in different tables with different lifecycles, and the sweep that flags them is
different code in a different service. `regulation` does not write `assistant`'s tables; it says
"this version has been diffed" by task name, and this module reads ``clause_diffs`` one-way and
flags its own rows.

**The citation is never rewritten.** Repointing it at the new version would silently change the
evidence behind a statement someone has already read and acted on, while the record still showed one
answer. It is flagged, the original stays resolvable, and re-asking the question produces a *new*
answer rather than editing the old one.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import structlog
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from regops_shared.models.base import utcnow

from .models import Answer, AnswerCitation

log = structlog.get_logger(__name__)


@dataclass(slots=True)
class SupersedeResult:
    document_version_id: uuid.UUID
    citations_superseded: int = 0
    answers_superseded: int = 0


def supersede_for_version(session: Session, version_id: uuid.UUID) -> SupersedeResult:
    """Flag every answer citation the amendment behind ``version_id`` invalidated.

    ``version_id`` is the **new** version. The paths that matter are those the diff touched in the
    *previous* one — that is where existing citations point — and additions are excluded: a clause
    that did not exist before cannot have been cited.
    """
    result = SupersedeResult(document_version_id=version_id)

    rows = session.execute(
        text(
            """
            SELECT d.id, d.from_version_id, coalesce(d.from_clause_path, d.clause_path)
            FROM clause_diffs d
            WHERE d.to_version_id = :version_id
              AND d.from_version_id IS NOT NULL
              AND d.change_kind <> 'added'
            """
        ),
        {"version_id": version_id},
    ).all()
    if not rows:
        return result

    touched: dict[tuple[uuid.UUID, str], uuid.UUID] = {(row[1], row[2]): row[0] for row in rows}

    citations = list(
        session.scalars(
            select(AnswerCitation).where(
                AnswerCitation.document_version_id.in_({key[0] for key in touched}),
                AnswerCitation.clause_path.in_({key[1] for key in touched}),
                AnswerCitation.superseded_at.is_(None),
            )
        )
    )
    if not citations:
        return result

    now = utcnow()
    answer_ids: set[uuid.UUID] = set()
    for citation in citations:
        diff_id = touched.get((citation.document_version_id, citation.clause_path))
        if diff_id is None:
            # The IN-pair query is a cross product of the two sets, so a citation can match one
            # version and another version's path. Only an exact pair is a supersession.
            continue
        citation.superseded_at = now
        citation.superseded_by_diff_id = diff_id
        answer_ids.add(citation.answer_id)
        result.citations_superseded += 1

    if answer_ids:
        # Flagging the citation is not enough: the *answer* is what a person reads, and one still
        # presented as current over evidence that has moved is the failure this exists to prevent.
        answers = list(
            session.scalars(
                select(Answer).where(Answer.id.in_(answer_ids), Answer.superseded_at.is_(None))
            )
        )
        for answer in answers:
            answer.superseded_at = now
        result.answers_superseded = len(answers)

    session.flush()
    log.info(
        "supersede.done",
        version=str(version_id),
        citations=result.citations_superseded,
        answers=result.answers_superseded,
    )
    return result


__all__ = ["SupersedeResult", "supersede_for_version"]
