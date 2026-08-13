"""Executing a scored run: ask every golden item, record what came back, pin the regime.

Two properties matter more than speed.

**Resumability.** A full run is 400 model-bound questions at roughly two minutes each. A harness
that lost everything on the 380th would never finish one, so each answer is appended to the run
artifact as it lands and a re-run skips items already recorded. The artifact — not this process —
is the run.

**The regime travels with the numbers.** A score is only meaningful per
``(rule_version, prompt_version, llm_model)``, and the model provenance is read back off the
``answers`` rows rather than off a constant: what the report needs is what actually answered, and
the two disagree the moment somebody edits a constant after a run.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from regops_shared.constants import (
    ANSWER_CONFIDENCE_THRESHOLD,
    ANSWER_PROMPT_VERSION,
    EMBEDDING_PASSAGE_VERSION,
    IR_PROMPT_VERSION,
    IR_RULE_VERSION,
    RETRIEVAL_VERSION,
    VERIFICATION_PROMPT_VERSION,
)
from regops_shared.db import sync_session

from . import client, corpus
from .client import EvaluationError, Services
from .goldenset import GoldenItem, GoldenSet
from .score import ObservedAnswer, ObservedCitation


@dataclass(slots=True)
class RunArtifact:
    """One scored run on disk. Append-only while it is being produced."""

    run_id: str
    cell: str
    started_at: str
    golden_set_version: str
    ra_signed_off: bool
    regime: dict[str, str] = field(default_factory=dict)
    observations: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> RunArtifact | None:
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            run_id=payload["run_id"],
            cell=payload["cell"],
            started_at=payload["started_at"],
            golden_set_version=payload["golden_set_version"],
            ra_signed_off=bool(payload.get("ra_signed_off", False)),
            regime=dict(payload.get("regime") or {}),
            observations=dict(payload.get("observations") or {}),
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "run_id": self.run_id,
                    "cell": self.cell,
                    "started_at": self.started_at,
                    "golden_set_version": self.golden_set_version,
                    "ra_signed_off": self.ra_signed_off,
                    "regime": self.regime,
                    "observations": self.observations,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )


def static_regime() -> dict[str, str]:
    """The versions the code is pinned at. The model actually used is read off the answers."""
    return {
        "ir_rule_version": IR_RULE_VERSION,
        "ir_prompt_version": IR_PROMPT_VERSION,
        "answer_prompt_version": ANSWER_PROMPT_VERSION,
        "verification_prompt_version": VERIFICATION_PROMPT_VERSION,
        "retrieval_version": RETRIEVAL_VERSION,
        "embedding_passage_version": EMBEDDING_PASSAGE_VERSION,
        "answer_confidence_threshold": str(ANSWER_CONFIDENCE_THRESHOLD),
    }


def execute(
    services: Services,
    *,
    golden: GoldenSet,
    cell_id: uuid.UUID,
    artifact_path: Path,
    items: Sequence[GoldenItem] | None = None,
    limit: int | None = None,
) -> RunArtifact:
    """Ask each item and record what came back. Resumes from ``artifact_path`` if it exists.

    Takes no session. A bounded run spends 40 minutes waiting on a model, and a connection held
    open across that is closed by the server underneath it — observed on the first full run, which
    died with ``server closed the connection unexpectedly`` at the resolution step after every
    answer had been collected. The database is touched only at the end, in its own short session,
    and ``pool_pre_ping`` can do its job on a fresh checkout.
    """
    artifact = RunArtifact.load(artifact_path) or RunArtifact(
        run_id=uuid.uuid4().hex[:12],
        cell=golden.cell,
        started_at=datetime.now(UTC).isoformat(),
        golden_set_version=golden.set_version,
        ra_signed_off=golden.ra_signed_off,
        regime=static_regime(),
    )

    queue = list(items if items is not None else golden.items)
    queue = [item for item in queue if item.id not in artifact.observations]
    if limit is not None:
        queue = queue[:limit]

    for index, item in enumerate(queue, start=1):
        print(f"[{index}/{len(queue)}] {item.id} ({item.axis.value}) …", flush=True)
        try:
            query_id = client.ask(
                services, question=item.question, cell_id=cell_id, cross_cell=item.cross_cell
            )
            answer, elapsed = client.await_answer(services, query_id)
        except EvaluationError as exc:
            artifact.observations[item.id] = {"error": str(exc)}
            artifact.save(artifact_path)
            continue

        artifact.observations[item.id] = {
            "query_id": str(query_id),
            "answer_id": answer.get("id"),
            "status": answer.get("status"),
            "no_answer_reason": answer.get("no_answer_reason"),
            "confidence": answer.get("confidence"),
            # ADR-0006 decision 8 is mechanically checkable and the effective-date axis exists to
            # check it: an answer that does not state the version it relied on looks identical to
            # one that does, and only the stored scope tells them apart.
            "effective_date_scope": answer.get("effective_date_scope"),
            "straddles_effective_date": answer.get("straddles_effective_date"),
            "elapsed_seconds": round(elapsed, 1),
            "text": answer.get("text"),
            "citations": [
                {
                    "claim_index": citation.get("claim_index"),
                    "document_version_id": citation.get("document_version_id"),
                    "clause_path": citation.get("clause_path"),
                }
                for citation in answer.get("citations") or []
            ],
            "provenance": answer.get("provenance") or {},
        }
        # The regime is read off the first real answer rather than assumed: what the report needs
        # is what actually answered.
        provenance = answer.get("provenance") or {}
        for key in ("llm_provider", "llm_model"):
            if provenance.get(key) and key not in artifact.regime:
                artifact.regime[key] = str(provenance[key])
        artifact.save(artifact_path)

    resolve_citations(artifact)
    artifact.save(artifact_path)
    return artifact


def resolve_citations(artifact: RunArtifact) -> None:
    """Stamp each stored citation with whether a clause exists at that path in that version.

    Done once at the end over the whole artifact rather than per answer: it is a database read per
    distinct pair, and a run of 200 items shares most of its pairs.
    """
    pairs: list[tuple[uuid.UUID, str]] = []
    for observation in artifact.observations.values():
        for citation in observation.get("citations") or []:
            if citation.get("document_version_id") and citation.get("clause_path"):
                pairs.append(
                    (uuid.UUID(str(citation["document_version_id"])), str(citation["clause_path"]))
                )
    if not pairs:
        return
    with sync_session() as session:
        resolved = corpus.citations_resolve(session, pairs)
    for observation in artifact.observations.values():
        for citation in observation.get("citations") or []:
            key = (
                uuid.UUID(str(citation["document_version_id"])),
                str(citation["clause_path"]),
            )
            citation["resolves"] = bool(resolved.get(key, False))


def unresolved_citations(artifact: RunArtifact) -> int:
    """Citations that have not been checked against the corpus yet.

    ``resolves`` **absent** and ``resolves: false`` are different facts, and reading the first as
    the second is how a run that crashed before its resolution pass reported a 100% hallucination
    rate on citations nobody had looked up. Observed on the first full run.
    """
    return sum(
        1
        for observation in artifact.observations.values()
        for citation in observation.get("citations") or []
        if "resolves" not in citation
    )


def observations_from(artifact: RunArtifact) -> dict[str, ObservedAnswer]:
    """Artifact → the shape :func:`~scripts.evaluation.score.score_queries` consumes.

    Raises if any citation is unresolved rather than defaulting it. The caller's job is to run
    :func:`resolve_citations` first; guessing here would put a fabricated-citation count into a
    gate report on the strength of a lookup that never happened.
    """
    pending = unresolved_citations(artifact)
    if pending:
        raise ValueError(
            f"{pending} citation(s) in run {artifact.run_id} have never been checked against the "
            f"corpus. Run resolve_citations() first — an unchecked citation is not a fabricated "
            f"one, and scoring it as one is a hallucination rate invented by the harness."
        )

    observed: dict[str, ObservedAnswer] = {}
    for item_id, row in artifact.observations.items():
        if row.get("error"):
            observed[item_id] = ObservedAnswer(item_id=item_id, status="error", error=row["error"])
            continue
        observed[item_id] = ObservedAnswer(
            item_id=item_id,
            status=str(row.get("status") or ""),
            citations=tuple(
                ObservedCitation(
                    document_version_id=str(citation.get("document_version_id") or ""),
                    clause_path=str(citation.get("clause_path") or ""),
                    resolves=bool(citation["resolves"]),
                )
                for citation in row.get("citations") or []
            ),
            no_answer_reason=row.get("no_answer_reason"),
            confidence=row.get("confidence"),
            elapsed_seconds=row.get("elapsed_seconds"),
            effective_date_scope=row.get("effective_date_scope"),
            straddles_effective_date=bool(row.get("straddles_effective_date")),
        )
    return observed


__all__ = [
    "RunArtifact",
    "execute",
    "observations_from",
    "resolve_citations",
    "static_regime",
    "unresolved_citations",
]
