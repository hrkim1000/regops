"""The evidence-verification agent — a separate pass with the power to fail an answer.

ADR-0006 decision 5 names two hallucination classes and counts both against the ≤ 2% gate:

| Class | Caught by |
|---|---|
| **Fabricated citation** — no such clause, or never retrieved | :mod:`.generate`, mechanically |
| **Mis-citation** — the clause exists, was retrieved, and does not support the claim | **here** |

The second is the dangerous one. It survives every structural check and looks correct to a reader
who does not open the citation, which is most readers. So this pass exists, it sees the claim and
the cited clause text and **not** the question — decision 6, because the question biases a verifier
toward agreeing that the answer addresses it — and its verdict can reject.

A verifier that only annotates is theatre. An ``unsupported`` verdict forces the answer to "needs
verification" rather than appending a caveat to a wrong answer.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass

import structlog

from regops_shared.constants import GENERATION_TEMPERATURE, VerificationVerdict
from regops_shared.llm import Completion, LLMClient

from .generate import Claim
from .prompts import VERIFY_SYSTEM_PROMPT, build_verification_prompt
from .store import Hit

log = structlog.get_logger(__name__)

_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)

#: Weight each verdict contributes to the confidence score. ``partial`` is deliberately half rather
#: than passing: a claim whose condition or limit is missing from the cited text is the shape of
#: near-miss that an RA has to catch, and it should push a borderline answer to review.
VERDICT_SCORE: dict[VerificationVerdict, float] = {
    VerificationVerdict.SUPPORTED: 1.0,
    VerificationVerdict.PARTIAL: 0.5,
    VerificationVerdict.UNSUPPORTED: 0.0,
}


@dataclass(slots=True)
class ClaimVerdict:
    """One claim, judged."""

    claim_index: int
    verdict: VerificationVerdict
    reason: str | None
    provider: str
    model: str


def verify_claims(
    client: LLMClient,
    *,
    claims: list[Claim],
    evidence: dict[tuple, Hit],
) -> list[ClaimVerdict]:
    """Judge each claim against the text it cites. One call per claim.

    One at a time, for the same reason extraction batches a single clause: a verifier shown several
    claims at once averages across them, and the whole point is that a single unsupported claim
    fails the answer.

    A claim whose cited clause text cannot be loaded is ``unsupported`` without asking a model.
    Evidence that cannot be produced is exactly the case the "needs verification" contract exists
    for, and inventing a verdict over missing text would be the mis-citation failure in the checker
    rather than in the answer.
    """
    verdicts: list[ClaimVerdict] = []
    for index, claim in enumerate(claims):
        cited = [
            (citation.clause_path, evidence[key].text)
            for citation in claim.citations
            if (key := (citation.document_version_id, citation.clause_path)) in evidence
        ]
        if not cited:
            verdicts.append(
                ClaimVerdict(
                    claim_index=index,
                    verdict=VerificationVerdict.UNSUPPORTED,
                    reason="cited clause text could not be resolved",
                    provider=client.provider,
                    model=client.model,
                )
            )
            continue

        completion = asyncio.run(
            client.complete(
                build_verification_prompt(claim=claim.text, evidence=cited),
                system=VERIFY_SYSTEM_PROMPT,
                temperature=GENERATION_TEMPERATURE,
            )
        )
        verdicts.append(parse_verdict(completion, claim_index=index))
    return verdicts


def parse_verdict(completion: Completion, *, claim_index: int) -> ClaimVerdict:
    """Read one verdict. An unreadable reply is ``unsupported``, never a pass by default.

    Split out so the failing path is testable without a model — the acceptance criterion is that a
    deliberately mis-cited answer *is failed*, and a fixture has to be able to prove it.
    """
    payload = _decode(completion.text)
    raw = str((payload or {}).get("verdict") or "").strip().lower()
    try:
        verdict = VerificationVerdict(raw)
    except ValueError:
        verdict = VerificationVerdict.UNSUPPORTED
        if payload is not None:
            log.warning("verify.unknown_verdict", verdict=raw, claim=claim_index)

    reason = str((payload or {}).get("reason") or "").strip() or None
    if payload is None:
        reason = "verifier returned nothing parseable"
        log.warning("verify.unparseable", claim=claim_index, model=completion.model)

    return ClaimVerdict(
        claim_index=claim_index,
        verdict=verdict,
        reason=reason,
        provider=completion.provider,
        model=completion.model,
    )


def verification_score(verdicts: list[ClaimVerdict]) -> float:
    """Mean verdict weight. No verdicts means nothing was checked, which scores zero."""
    if not verdicts:
        return 0.0
    return sum(VERDICT_SCORE[verdict.verdict] for verdict in verdicts) / len(verdicts)


def rejected(verdicts: list[ClaimVerdict]) -> bool:
    """Whether any claim was rejected outright — one is enough to fail the answer."""
    return any(verdict.verdict is VerificationVerdict.UNSUPPORTED for verdict in verdicts)


def _decode(text: str) -> dict | None:
    stripped = (text or "").strip()
    if not stripped:
        return None
    for candidate in (stripped, *(m.group(0) for m in [_JSON_OBJECT.search(stripped)] if m)):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


__all__ = [
    "VERDICT_SCORE",
    "ClaimVerdict",
    "parse_verdict",
    "rejected",
    "verification_score",
    "verify_claims",
]
