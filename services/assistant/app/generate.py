"""The citation-enforced generation agent.

An **agent** under all three of ADR-0008's tests: it invokes an LLM, it writes rows carrying
provenance, and its output cannot be trusted without a separate check — here, the evidence
verification pass that follows it and can fail the answer outright.

What this module does *not* do is decide what may be cited. Retrieval already fixed that set, and
every citation the model returns is resolved back against it before it can reach a row (ADR-0006
decision 4):

- a passage number outside the retrieved set → the claim is rejected as fabricated
- a clause path the passage does not cover → the same
- a claim with no citation at all → dropped; an answer with no cited claim becomes
  "needs verification"

That check is mechanical and runs before any model-based verification. It kills the cheapest
hallucination there is — a plausible-looking 조문 번호 produced from memory — without spending a
second inference on it.
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from dataclasses import dataclass, field

import structlog

from regops_shared.constants import (
    GENERATION_TEMPERATURE,
    MAX_CLAIMS_PER_ANSWER,
    NoAnswerReason,
)
from regops_shared.llm import Completion, LLMClient

from .prompts import ANSWER_SYSTEM_PROMPT, build_answer_prompt
from .retrieval import RetrievalResult

log = structlog.get_logger(__name__)

#: A chatty model wraps JSON in a fence or a sentence. Pull the outermost object rather than
#: failing: discarding a correct answer over formatting shows up as a "needs verification" rate that
#: no amount of threshold tuning explains.
_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


@dataclass(slots=True)
class Citation:
    """One resolved citation: a real clause, in a real version, that retrieval actually returned."""

    document_version_id: uuid.UUID
    clause_path: str


@dataclass(slots=True)
class Claim:
    """One factual statement and the clauses it rests on. A claim without citations cannot exist."""

    text: str
    citations: list[Citation] = field(default_factory=list)


@dataclass(slots=True)
class GenerationResult:
    """What generation produced, and what was thrown away producing it."""

    #: Composed from the surviving claims, never taken from the model as free text. A prose field
    #: alongside the claims would be the one thing a reader actually reads and the one thing no
    #: citation check ever touched.
    answer: str = ""
    claims: list[Claim] = field(default_factory=list)
    provider: str = ""
    model: str = ""
    #: Set when the reply cannot be used at all. Distinct from "answered with no claims", which is
    #: the legitimate "these passages do not answer the question" verdict.
    reason: NoAnswerReason | None = None
    #: Citations the model produced that named something retrieval never returned. Counted because
    #: a rising rate is a prompt regression, and it is invisible if rejections leave no trace.
    fabricated: list[str] = field(default_factory=list)

    @property
    def usable(self) -> bool:
        return bool(self.claims) and self.reason is None


def generate(client: LLMClient, *, question: str, retrieval: RetrievalResult) -> GenerationResult:
    """Answer from the retrieved passages, or decline. Synchronous, because Celery workers are."""
    prompt = build_answer_prompt(
        question=question,
        hits=retrieval.hits,
        versions=retrieval.versions,
        effective_date_scope=retrieval.effective_date_scope,
        straddles=retrieval.straddles_effective_date,
    )
    completion = asyncio.run(
        client.complete(prompt, system=ANSWER_SYSTEM_PROMPT, temperature=GENERATION_TEMPERATURE)
    )
    return parse_completion(completion, retrieval=retrieval)


def parse_completion(completion: Completion, *, retrieval: RetrievalResult) -> GenerationResult:
    """Validate a raw completion into cited claims. Split out so it is testable without a model."""
    result = GenerationResult(provider=completion.provider, model=completion.model)

    payload = _decode(completion.text)
    if payload is None:
        result.reason = NoAnswerReason.UNPARSEABLE
        log.warning("generate.unparseable", model=completion.model)
        return result

    allowed = retrieval.citable_paths()

    raw_claims = payload.get("claims")
    if not isinstance(raw_claims, list):
        raw_claims = []

    for item in raw_claims[:MAX_CLAIMS_PER_ANSWER]:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        citations, fabricated = _resolve(item.get("cites"), retrieval=retrieval, allowed=allowed)
        result.fabricated.extend(fabricated)
        if not citations:
            # Decision 4, applied per claim: an uncited sentence is not downgraded with a caveat,
            # it is removed. What is left either stands on evidence or the answer refuses.
            log.info("generate.uncited_claim", claim=text[:120])
            continue
        result.claims.append(Claim(text=text, citations=citations))

    if result.fabricated:
        # A fabricated citation fails the whole answer rather than only its claim. The model has
        # demonstrated it is producing clause numbers from memory, and the remaining claims were
        # produced by the same pass.
        result.reason = NoAnswerReason.FABRICATED_CITATION
        log.warning("generate.fabricated_citation", cites=result.fabricated[:5])
        return result

    if not result.claims:
        result.reason = NoAnswerReason.NO_CITATION
        return result

    # The answer *is* the claims. There is no free-text field to read instead, which closes a real
    # hole in decision 4: the prose a reader sees was previously an unvalidated string beside the
    # validated claims, so every citation check applied to text nobody was shown. Composing it here
    # means every sentence rendered has a citation and goes on to face verification.
    result.answer = "\n".join(claim.text for claim in result.claims)
    return result


def _resolve(
    raw: object, *, retrieval: RetrievalResult, allowed: set[tuple[uuid.UUID, str]]
) -> tuple[list[Citation], list[str]]:
    """Turn the model's ``cites`` into real ``(version, clause_path)`` pairs.

    Passage numbers rather than version ids: a model cannot be asked to reproduce a UUID, and a bare
    clause path is ambiguous — 제8조 exists in all nine 법령 of the gated corpus.
    """
    citations: list[Citation] = []
    fabricated: list[str] = []

    for entry in _as_list(raw):
        number, path = _read_cite(entry)
        if number is None or not (1 <= number <= len(retrieval.hits)):
            fabricated.append(f"passage={number!r} path={path!r}")
            continue
        hit = retrieval.hits[number - 1]
        target = path or hit.clause_path
        key = (hit.document_version_id, target)
        if key not in allowed:
            fabricated.append(f"passage={number} path={target!r}")
            continue
        citation = Citation(document_version_id=hit.document_version_id, clause_path=target)
        if citation not in citations:
            citations.append(citation)

    return citations, fabricated


def _read_cite(entry: object) -> tuple[int | None, str | None]:
    """Accept the documented object form, and the bare passage number a model sometimes returns."""
    if isinstance(entry, dict):
        number = _as_int(entry.get("passage"))
        path = entry.get("clause_path")
        return number, str(path).strip() if path else None
    return _as_int(entry), None


def _as_int(value: object) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _as_list(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    return [value] if value is not None else []


def _decode(text: str) -> dict | None:
    """The outermost JSON object, or ``None``."""
    stripped = (text or "").strip()
    if not stripped:
        return None
    for candidate in _candidates(stripped):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _candidates(text: str) -> list[str]:
    out = [text]
    match = _JSON_OBJECT.search(text)
    if match:
        out.append(match.group(0))
    return out


__all__ = ["Citation", "Claim", "GenerationResult", "generate", "parse_completion"]
