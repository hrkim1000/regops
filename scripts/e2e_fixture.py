"""The one fixture the Playwright suite cannot read off the real corpus.

Three of the four E2E journeys run on ingested data with nothing seeded — alerts composed from real
change events, answers produced by the real model. The fourth cannot: **a superseded citation needs
an answer that cites a clause an amendment later touched**, and today no answer in the corpus does.
The two answers pinned to a version that *was* amended cite 제6장/제36조 while the amendment moved
제1장/제2조 and 제2장/제7조, so the sweep that flags them correctly flags nothing.

Manufacturing that intersection any other way means either re-diffing a live version, or asking the
model and hoping it happens to cite the one amended clause. Both replace a deterministic check with
a coin flip. So this seeds **one answer**, pinned to a clause a real ``clause_diff`` really moved,
and then the suite runs the **real** ``assistant.supersede_answer_citations`` task — the same task,
by the same name, that `regulation`'s diff stage sends when an amendment lands. The model plays no
part in that path: superseding is deterministic SQL over ``clause_diffs``.

The seeded rows are marked with :data:`MARKER` in the question text and ``fixture`` provenance, so
``clean`` removes exactly what ``seed`` wrote and nothing that a person asked.

Run inside the stack — `regulation` is the container that carries /scripts::

    docker compose exec -T regulation python /scripts/e2e_fixture.py seed --cell mfds_cosmetic
    docker compose exec -T regulation python /scripts/e2e_fixture.py supersede --version-id <uuid>
    docker compose exec -T regulation python /scripts/e2e_fixture.py clean

Every subcommand prints one JSON object on stdout; the suite reads it.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import date

from celery import Celery
from sqlalchemy import delete, select, text

from regops_shared.constants import AnswerStatus
from regops_shared.db import sync_session
from regops_shared.models import Answer, AnswerCitation, Cell, Query, User
from regops_shared.settings import get_settings

#: In the question text, so a stray fixture row is identifiable in the UI and in the database.
MARKER = "[e2e-fixture]"

#: Who the seeded question is attributed to. The E2E suite signs in as its own principal, so the
#: fixture uses it too rather than putting an automated row under a person's name — ``asked_by`` is
#: a foreign key into the audit story, not a display field. Absent, it stays null.
ASKED_BY_EMAIL = "e2e-ra@example.com"

#: Written into the provenance columns. `llm_provider` is where an answer records what produced it
#: (ADR-0008), and a fixture claiming `ollama` would be a lie in exactly the column that exists to
#: prevent one.
FIXTURE_PROVENANCE = "fixture"


def _cell(session, slug: str) -> Cell:
    authority, _, domain = slug.partition("_")
    cell = session.execute(
        select(Cell).where(Cell.authority == authority, Cell.domain == domain)
    ).scalar_one_or_none()
    if cell is None:
        raise SystemExit(f"no such cell: {slug}")
    return cell


def _amended_clause(session, cell_id: uuid.UUID) -> dict[str, object]:
    """A clause that a real amendment really moved, inside this cell.

    ``from_version_id`` is where an existing citation would point, so that is the version the
    seeded citation pins. ``added`` is excluded for the same reason the sweep excludes it: a clause
    that did not exist before cannot have been cited.
    """
    row = session.execute(
        text(
            """
            SELECT d.to_version_id,
                   d.from_version_id,
                   coalesce(d.from_clause_path, d.clause_path) AS clause_path,
                   v.document_id,
                   v.effective_date
            FROM clause_diffs d
            JOIN document_versions v ON v.id = d.from_version_id
            JOIN document_cells dc ON dc.document_id = v.document_id
            WHERE d.from_version_id IS NOT NULL
              AND d.change_kind <> 'added'
              AND dc.cell_id = :cell_id
            ORDER BY d.change_kind = 'modified' DESC, d.created_at
            LIMIT 1
            """
        ),
        {"cell_id": str(cell_id)},
    ).first()
    if row is None:
        raise SystemExit(
            "no amended clause in this cell — the superseded-citation journey needs at least one "
            "document version that has been diffed against a previous one"
        )
    return {
        "to_version_id": row[0],
        "from_version_id": row[1],
        "clause_path": row[2],
        "document_id": row[3],
        "effective_date": row[4],
    }


def seed(cell_slug: str) -> dict[str, object]:
    """One answered answer, citing a clause a real amendment already moved."""
    with sync_session() as session:
        cell = _cell(session, cell_slug)
        target = _amended_clause(session, cell.id)
        asker = session.execute(
            select(User).where(User.email == ASKED_BY_EMAIL)
        ).scalar_one_or_none()

        query = Query(
            cell_id=cell.id,
            cross_cell=False,
            text=f"{MARKER} 이 조문의 요건은 무엇입니까?",
            asked_by=asker.id if asker else None,
        )
        session.add(query)
        session.flush()

        answer = Answer(
            query_id=query.id,
            text=f"{MARKER} 근거가 개정되었을 때의 표시를 확인하기 위한 고정 답변입니다.",
            status=AnswerStatus.ANSWERED,
            confidence=0.9,
            document_version_scope=[target["from_version_id"]],
            effective_date_scope=target["effective_date"] or date.today(),
            straddles_effective_date=False,
            llm_provider=FIXTURE_PROVENANCE,
            llm_model=FIXTURE_PROVENANCE,
            prompt_version=FIXTURE_PROVENANCE,
            retrieval_version=FIXTURE_PROVENANCE,
        )
        session.add(answer)
        session.flush()

        session.add(
            AnswerCitation(
                answer_id=answer.id,
                claim_index=0,
                document_id=target["document_id"],
                document_version_id=target["from_version_id"],
                clause_path=target["clause_path"],
                effective_date=target["effective_date"],
            )
        )
        session.commit()

        return {
            "answer_id": str(answer.id),
            "query_id": str(query.id),
            "cell": cell_slug,
            "clause_path": target["clause_path"],
            "cited_version_id": str(target["from_version_id"]),
            "amended_version_id": str(target["to_version_id"]),
        }


def supersede(version_id: str) -> dict[str, object]:
    """Send the real task, on the real queue, by name — exactly as the diff stage does."""
    settings = get_settings()
    app = Celery(broker=settings.redis_url, backend=settings.redis_url)
    result = app.send_task(
        "assistant.supersede_answer_citations", args=[version_id], queue="assistant"
    )
    return {"task_id": result.id, "document_version_id": version_id}


def clean() -> dict[str, object]:
    """Remove exactly what ``seed`` wrote — marked rows only, never a question a person asked."""
    with sync_session() as session:
        query_ids = list(
            session.execute(select(Query.id).where(Query.text.like(f"{MARKER}%"))).scalars()
        )
        if not query_ids:
            return {"queries_removed": 0, "answers_removed": 0}

        answer_ids = list(
            session.execute(select(Answer.id).where(Answer.query_id.in_(query_ids))).scalars()
        )
        if answer_ids:
            session.execute(delete(AnswerCitation).where(AnswerCitation.answer_id.in_(answer_ids)))
            session.execute(delete(Answer).where(Answer.id.in_(answer_ids)))
        session.execute(delete(Query).where(Query.id.in_(query_ids)))
        session.commit()
        return {"queries_removed": len(query_ids), "answers_removed": len(answer_ids)}


def main() -> int:
    """Dispatch one subcommand and print its result as a single JSON object."""
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    seed_parser = sub.add_parser("seed", help="one answer citing an already-amended clause")
    seed_parser.add_argument("--cell", default="mfds_cosmetic")

    supersede_parser = sub.add_parser("supersede", help="dispatch the real supersede task")
    supersede_parser.add_argument("--version-id", required=True)

    sub.add_parser("clean", help="remove everything seed wrote")

    args = parser.parse_args()
    match args.command:
        case "seed":
            payload = seed(args.cell)
        case "supersede":
            payload = supersede(args.version_id)
        case "clean":
            payload = clean()
        case unknown:  # pragma: no cover - argparse rejects anything else
            raise SystemExit(f"unknown command: {unknown}")

    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
