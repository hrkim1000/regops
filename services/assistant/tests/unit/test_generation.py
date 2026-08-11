"""The mechanical citation check — ADR-0006 decision 4.

"Generation may only cite what retrieval returned" is either enforced or it is a wish. These tests
are the enforcement: a passage number outside the retrieved set, a clause path the passage does not
cover, and a claim with no citation at all each have a defined, tested outcome, and none of them is
"store it anyway with a caveat".
"""

from __future__ import annotations

import json
import uuid
from datetime import date

from app.generate import parse_completion
from app.retrieval import RetrievalResult
from app.store import Hit, VersionRef
from regops_shared.constants import MAX_CLAIMS_PER_ANSWER, NoAnswerReason
from regops_shared.llm import Completion

VERSION = uuid.uuid4()
DOCUMENT = uuid.uuid4()


def retrieval() -> RetrievalResult:
    return RetrievalResult(
        hits=[
            Hit(
                clause_id=uuid.uuid4(),
                clause_path="제8조",
                document_version_id=VERSION,
                heading="영업의 금지",
                text="누구든지 변패된 화장품을 판매하여서는 아니 된다.",
                kind="prose",
                effective_date=date(2026, 4, 2),
                score=1.0,
                child_clause_paths=("제8조", "제8조/제1항"),
            )
        ],
        versions=[
            VersionRef(
                version_id=VERSION,
                document_id=DOCUMENT,
                document_title="화장품법",
                effective_date=date(2026, 4, 2),
                language="ko",
            )
        ],
    )


def completion(payload: object) -> Completion:
    body = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    return Completion(text=body, provider="stub", model="stub-model")


def test_a_cited_claim_resolves_to_a_real_version_and_path() -> None:
    result = parse_completion(
        completion(
            {
                "answer": "변패된 화장품은 판매할 수 없습니다.",
                "claims": [
                    {
                        "text": "변패된 화장품 판매는 금지된다.",
                        "cites": [{"passage": 1, "clause_path": "제8조/제1항"}],
                    }
                ],
            }
        ),
        retrieval=retrieval(),
    )

    assert result.usable
    assert result.claims[0].citations[0].document_version_id == VERSION
    assert result.claims[0].citations[0].clause_path == "제8조/제1항"


def test_a_citation_naming_a_passage_that_was_never_retrieved_fails_the_answer() -> None:
    """Decision 4: rejected outright. This is the cheapest hallucination there is."""
    result = parse_completion(
        completion({"answer": "x", "claims": [{"text": "y", "cites": [{"passage": 7}]}]}),
        retrieval=retrieval(),
    )

    assert not result.usable
    assert result.reason is NoAnswerReason.FABRICATED_CITATION
    assert result.fabricated


def test_a_clause_path_the_passage_does_not_cover_is_fabricated() -> None:
    """The passage covers 제8조 and 제8조/제1항. 제99조 was produced from memory."""
    result = parse_completion(
        completion(
            {
                "answer": "x",
                "claims": [{"text": "y", "cites": [{"passage": 1, "clause_path": "제99조"}]}],
            }
        ),
        retrieval=retrieval(),
    )

    assert result.reason is NoAnswerReason.FABRICATED_CITATION


def test_an_uncited_claim_is_dropped_rather_than_hedged() -> None:
    """A sentence that cannot be cited does not belong in the answer at all."""
    result = parse_completion(
        completion(
            {
                "answer": "x",
                "claims": [
                    {"text": "cited", "cites": [{"passage": 1}]},
                    {"text": "uncited", "cites": []},
                ],
            }
        ),
        retrieval=retrieval(),
    )

    assert [claim.text for claim in result.claims] == ["cited"]


def test_an_answer_with_no_cited_claim_becomes_needs_verification() -> None:
    """Acceptance criterion: never a hedged prose answer."""
    result = parse_completion(
        completion({"answer": "아마도 금지됩니다.", "claims": []}), retrieval=retrieval()
    )

    assert not result.usable
    assert result.reason is NoAnswerReason.NO_CITATION


def test_an_unparseable_reply_is_recorded_not_guessed_at() -> None:
    result = parse_completion(completion("I'm not sure, sorry!"), retrieval=retrieval())

    assert result.reason is NoAnswerReason.UNPARSEABLE


def test_json_wrapped_in_prose_is_still_read() -> None:
    """Discarding a correct answer over formatting shows up as an unexplainable refusal rate."""
    raw = (
        "Sure! Here is the JSON:\n```json\n"
        + json.dumps({"answer": "a", "claims": [{"text": "t", "cites": [{"passage": 1}]}]})
        + "\n```"
    )

    result = parse_completion(completion(raw), retrieval=retrieval())

    assert result.usable


def test_a_bare_passage_number_is_accepted_as_a_citation() -> None:
    """Models return this shape often enough that rejecting it would only measure prompt luck."""
    result = parse_completion(
        completion({"answer": "a", "claims": [{"text": "t", "cites": [1]}]}),
        retrieval=retrieval(),
    )

    assert result.usable
    assert result.claims[0].citations[0].clause_path == "제8조"


def test_duplicate_citations_within_a_claim_are_collapsed() -> None:
    result = parse_completion(
        completion(
            {
                "answer": "a",
                "claims": [{"text": "t", "cites": [{"passage": 1}, {"passage": 1}]}],
            }
        ),
        retrieval=retrieval(),
    )

    assert len(result.claims[0].citations) == 1


def test_a_runaway_reply_is_truncated() -> None:
    """Real regulatory answers are a handful of claims; more than the cap is a loop, not rigour."""
    claims = [
        {"text": f"claim {index}", "cites": [{"passage": 1}]}
        for index in range(MAX_CLAIMS_PER_ANSWER + 5)
    ]

    result = parse_completion(completion({"answer": "a", "claims": claims}), retrieval=retrieval())

    assert len(result.claims) == MAX_CLAIMS_PER_ANSWER


def test_provenance_travels_with_the_result() -> None:
    """Every answers row carries provider/model — it starts here."""
    result = parse_completion(
        completion({"answer": "a", "claims": [{"text": "t", "cites": [{"passage": 1}]}]}),
        retrieval=retrieval(),
    )

    assert (result.provider, result.model) == ("stub", "stub-model")


def test_the_answer_is_composed_from_the_validated_claims() -> None:
    """Decision 4 had a hole: the prose a reader sees was an unvalidated free-text field.

    Every citation check applied to `claims`, and the page rendered `answer` — so the one string
    anybody read was the one string nothing checked. The answer is now the claims.
    """
    result = parse_completion(
        completion(
            {
                "claims": [
                    {"text": "기록은 3년간 보관하여야 한다.", "cites": [{"passage": 1}]},
                    {"text": "위반 시 등록이 취소된다.", "cites": [{"passage": 1}]},
                ]
            }
        ),
        retrieval=retrieval(),
    )

    assert result.answer == "기록은 3년간 보관하여야 한다.\n위반 시 등록이 취소된다."


def test_a_free_text_answer_field_is_ignored() -> None:
    """Prose a model volunteers is not rendered — it was never citation-constrained."""
    result = parse_completion(
        completion(
            {
                "answer": "아마 5년일 것입니다.",
                "claims": [{"text": "기록은 3년간 보관하여야 한다.", "cites": [{"passage": 1}]}],
            }
        ),
        retrieval=retrieval(),
    )

    assert "5년" not in result.answer
    assert result.answer == "기록은 3년간 보관하여야 한다."


def test_a_refusal_carries_no_answer_text() -> None:
    result = parse_completion(completion({"claims": []}), retrieval=retrieval())

    assert result.answer == ""
