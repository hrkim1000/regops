"""The blind assessment worksheet — how the two human-judged gates actually get measured.

Citation accuracy and hallucination rate are readings, not computations: whether a clause *supports*
a claim, and whether an answer *contradicts* its source, are judgements only a person reading both
can make. The harness's job is to put that judgement in front of an assessor without also putting
the answer in front of them.

So the worksheet carries the claim and the cited clause text, and deliberately omits three things
the run artifact holds: the golden item's ``expected_answer``, its ``expected_clause_paths``, and
the system's own confidence and verification verdicts. An assessor who can see that the system was
confident, or that the cited path is the one the set expected, is no longer assessing blind — they
are checking agreement, which is a different and much easier question.

Rows are shuffled by a **recorded seed** rather than left in run order. Run order groups items by
axis, and an assessor who has just worked through thirty identifier lookups reads the thirty-first
differently. The seed is written into the worksheet so the shuffle is reproducible and auditable —
an unrecorded shuffle would make it impossible to show later that the order was not chosen.
"""

from __future__ import annotations

import csv
import json
import random
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from . import corpus
from .run import RunArtifact
from .score import AssessedCitation

#: The columns an assessor fills in. Everything else is read-only context.
ANSWER_COLUMNS = ("supports", "contradicts", "assessor_note")

HEADER = (
    "row_id",
    "item_id",
    "claim_index",
    "clause_path",
    "question",
    "answer_claim",
    "cited_clause_text",
    *ANSWER_COLUMNS,
)


@dataclass(frozen=True, slots=True)
class WorksheetRow:
    row_id: str
    item_id: str
    claim_index: int
    clause_path: str
    question: str
    answer_claim: str
    cited_clause_text: str


def build(
    session: Session,
    artifact: RunArtifact,
    *,
    questions: dict[str, str],
    seed: int,
) -> tuple[list[WorksheetRow], int]:
    """One row per (answer, citation). Returns the rows and the seed they were shuffled with."""
    rows: list[WorksheetRow] = []
    for item_id, observation in artifact.observations.items():
        if observation.get("error") or observation.get("status") != "answered":
            continue
        claims = str(observation.get("text") or "").split("\n")
        for citation in observation.get("citations") or []:
            version_id = citation.get("document_version_id")
            path = str(citation.get("clause_path") or "")
            if not version_id or not path:
                continue
            texts = corpus.clause_texts(session, uuid.UUID(str(version_id)), [path])
            claim_index = int(citation.get("claim_index") or 0)
            rows.append(
                WorksheetRow(
                    row_id=uuid.uuid4().hex[:8],
                    item_id=item_id,
                    claim_index=claim_index,
                    clause_path=path,
                    question=questions.get(item_id, ""),
                    answer_claim=(
                        claims[claim_index] if 0 <= claim_index < len(claims) else "\n".join(claims)
                    ),
                    cited_clause_text=texts.get(path, "[본문을 찾지 못함 — 존재하지 않는 인용]"),
                )
            )
    random.Random(seed).shuffle(rows)
    return rows, seed


def write(rows: list[WorksheetRow], path: Path, *, seed: int, run_id: str) -> None:
    """CSV, because an RA fills this in a spreadsheet, and UTF-8 BOM so Excel opens 한글 correctly.

    The provenance line goes into a sidecar rather than into the CSV: a comment row inside the file
    is one accidental sort away from being mixed into the data.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADER)
        for row in rows:
            writer.writerow(
                [
                    row.row_id,
                    row.item_id,
                    row.claim_index,
                    row.clause_path,
                    row.question,
                    row.answer_claim,
                    row.cited_clause_text,
                    "",
                    "",
                    "",
                ]
            )
    path.with_suffix(".meta.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "shuffle_seed": seed,
                "rows": len(rows),
                "blind": (
                    "expected_answer, expected_clause_paths, confidence and verification verdicts "
                    "are deliberately absent — an assessor who can see them is checking agreement, "
                    "not assessing support"
                ),
                "instructions": {
                    "supports": "y | n — does the cited clause support this claim?",
                    "contradicts": "y | n — does the claim contradict the cited text?",
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def read(path: Path) -> list[AssessedCitation]:
    """Read a filled worksheet. An unfilled ``supports`` is an error, never a silent ``no``.

    Treating a blank as "does not support" would let a half-finished worksheet report a failing
    citation-accuracy gate, and treating it as "supports" would do the opposite. Both are the
    assessor's answer being invented for them.
    """
    rows: list[AssessedCitation] = []
    blanks: list[str] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for record in csv.DictReader(handle):
            supports = _tri(record.get("supports"))
            if supports is None:
                blanks.append(record.get("row_id") or "?")
                continue
            rows.append(
                AssessedCitation(
                    item_id=str(record["item_id"]),
                    claim_index=int(record.get("claim_index") or 0),
                    clause_path=str(record.get("clause_path") or ""),
                    supports=supports,
                    contradicts=bool(_tri(record.get("contradicts"))),
                )
            )
    if blanks:
        raise ValueError(
            f"{len(blanks)} worksheet row(s) have no 'supports' judgement "
            f"({', '.join(blanks[:5])}…). A blank is not a verdict — finish the worksheet or "
            f"remove the rows deliberately."
        )
    return rows


def _tri(value: Any) -> bool | None:
    text = str(value or "").strip().lower()
    if text in {"y", "yes", "true", "1", "예", "o"}:
        return True
    if text in {"n", "no", "false", "0", "아니오", "x"}:
        return False
    return None


__all__ = ["ANSWER_COLUMNS", "HEADER", "WorksheetRow", "build", "read", "write"]
