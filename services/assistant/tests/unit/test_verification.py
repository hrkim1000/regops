"""The evidence-verification pass and the routing it drives — ADR-0006 decisions 5 and 6.

The claim under test is that the verifier can *fail* an answer. A verifier that only annotates is
theatre, so the interesting cases are the ones where something goes wrong: an unsupported verdict,
an unreadable reply, and a citation whose clause text could not be loaded at all.
"""

from __future__ import annotations

import json
import uuid

from app.ask import route
from app.generate import Citation, Claim
from app.store import Hit
from app.verify import ClaimVerdict, parse_verdict, rejected, verification_score, verify_claims
from regops_shared.constants import (
    ANSWER_CONFIDENCE_THRESHOLD,
    AnswerStatus,
    NoAnswerReason,
    VerificationVerdict,
)
from regops_shared.llm import Completion, LLMClient

VERSION = uuid.uuid4()


class ScriptedLLM(LLMClient):
    """Answers each ``complete`` call from a list, and records the prompts it was given."""

    provider = "stub"

    def __init__(self, replies: list[dict | str]) -> None:
        self.model = "stub-model"
        self._replies = list(replies)
        self.prompts: list[str] = []

    async def complete(self, prompt, *, system=None, temperature=None) -> Completion:
        self.prompts.append(prompt)
        reply = self._replies.pop(0) if self._replies else {"verdict": "unsupported"}
        body = reply if isinstance(reply, str) else json.dumps(reply, ensure_ascii=False)
        return Completion(text=body, provider=self.provider, model=self.model)

    async def embed(self, text: str) -> list[float]:  # pragma: no cover - unused here
        return [0.0]


def verdict(value: VerificationVerdict, index: int = 0) -> ClaimVerdict:
    return ClaimVerdict(
        claim_index=index, verdict=value, reason=None, provider="stub", model="stub-model"
    )


def evidence(path: str = "제8조", body: str = "판매하여서는 아니 된다.") -> dict:
    return {
        (VERSION, path): Hit(
            clause_id=uuid.uuid4(),
            clause_path=path,
            document_version_id=VERSION,
            heading=None,
            text=body,
            kind="prose",
            effective_date=None,
            score=1.0,
        )
    }


def claim(text: str = "판매가 금지된다.", path: str = "제8조") -> Claim:
    return Claim(text=text, citations=[Citation(document_version_id=VERSION, clause_path=path)])


# --- reading a verdict -----------------------------------------------------------------------


def test_supported_verdict_is_read() -> None:
    result = parse_verdict(
        Completion(text='{"verdict": "supported", "reason": "states it"}', provider="s", model="m"),
        claim_index=0,
    )

    assert result.verdict is VerificationVerdict.SUPPORTED
    assert result.reason == "states it"


def test_an_unreadable_reply_is_unsupported_never_a_pass() -> None:
    """A wrong "supported" lets an unverifiable statement reach an RA as fact."""
    result = parse_verdict(Completion(text="hmm", provider="s", model="m"), claim_index=0)

    assert result.verdict is VerificationVerdict.UNSUPPORTED


def test_an_unknown_verdict_word_is_unsupported() -> None:
    result = parse_verdict(
        Completion(text='{"verdict": "probably"}', provider="s", model="m"), claim_index=0
    )

    assert result.verdict is VerificationVerdict.UNSUPPORTED


# --- the pass --------------------------------------------------------------------------------


def test_the_verifier_is_not_shown_the_question() -> None:
    """Decision 6. A verifier shown the question drifts toward confirming the answer fits."""
    client = ScriptedLLM([{"verdict": "supported"}])

    verify_claims(client, claims=[claim()], evidence=evidence())

    assert "판매가 금지된다." in client.prompts[0]
    assert "판매하여서는 아니 된다." in client.prompts[0]
    assert "Question:" not in client.prompts[0]


def test_each_claim_is_judged_on_its_own() -> None:
    """A verifier shown several claims at once averages across them."""
    client = ScriptedLLM([{"verdict": "supported"}, {"verdict": "unsupported"}])

    verdicts = verify_claims(client, claims=[claim("a"), claim("b")], evidence=evidence())

    assert len(client.prompts) == 2
    assert [v.verdict for v in verdicts] == [
        VerificationVerdict.SUPPORTED,
        VerificationVerdict.UNSUPPORTED,
    ]


def test_a_claim_whose_evidence_cannot_be_loaded_is_unsupported_without_asking_a_model() -> None:
    """Evidence that cannot be produced is exactly what "needs verification" exists for."""
    client = ScriptedLLM([{"verdict": "supported"}])

    verdicts = verify_claims(client, claims=[claim(path="제99조")], evidence=evidence())

    assert verdicts[0].verdict is VerificationVerdict.UNSUPPORTED
    assert client.prompts == []


def test_verification_score_weights_partial_at_half() -> None:
    score = verification_score(
        [verdict(VerificationVerdict.SUPPORTED), verdict(VerificationVerdict.PARTIAL, 1)]
    )

    assert score == 0.75


def test_nothing_checked_scores_zero() -> None:
    assert verification_score([]) == 0.0


def test_one_unsupported_claim_rejects() -> None:
    assert rejected(
        [verdict(VerificationVerdict.SUPPORTED), verdict(VerificationVerdict.UNSUPPORTED, 1)]
    )


def test_partial_alone_does_not_reject() -> None:
    assert not rejected([verdict(VerificationVerdict.PARTIAL)])


# --- routing ---------------------------------------------------------------------------------


def test_a_rejected_claim_forces_needs_verification_whatever_the_confidence() -> None:
    """Acceptance criterion: a deliberately mis-cited answer is failed by the verification pass."""
    status, reason = route(0.99, verdicts=[verdict(VerificationVerdict.UNSUPPORTED)])

    assert status is AnswerStatus.NEEDS_VERIFICATION
    assert reason is NoAnswerReason.UNSUPPORTED_CLAIM


def test_sub_threshold_confidence_routes_to_review() -> None:
    """Acceptance criterion: it does not reach the user as final."""
    status, reason = route(
        ANSWER_CONFIDENCE_THRESHOLD - 0.01, verdicts=[verdict(VerificationVerdict.PARTIAL)]
    )

    assert status is AnswerStatus.NEEDS_REVIEW
    assert reason is None


def test_a_supported_confident_answer_is_final() -> None:
    status, _ = route(0.9, verdicts=[verdict(VerificationVerdict.SUPPORTED)])

    assert status is AnswerStatus.ANSWERED
