"""Confidence scoring and the statement every answer has to carry — ADR-0006 decision 8.

An answer that travels without its effective date will eventually be read against the wrong version
of the law. Rendering it is therefore part of producing the answer, not a presentation choice a
caller may skip.
"""

from __future__ import annotations

import uuid
from datetime import date

from app.ask import EFFECTIVE_DATE_NOTICE, STRADDLE_NOTICE, render, score
from app.generate import Citation, Claim
from app.retrieval import RetrievalResult
from app.store import Hit, VersionRef
from app.verify import ClaimVerdict
from regops_shared.constants import (
    CONFIDENCE_RETRIEVAL_WEIGHT,
    CONFIDENCE_VERIFICATION_WEIGHT,
    VerificationVerdict,
)

VERSION = uuid.uuid4()


def version(language: str = "ko", effective: date | None = date(2026, 4, 2)) -> VersionRef:
    return VersionRef(
        version_id=VERSION,
        document_id=uuid.uuid4(),
        document_title="화장품법",
        effective_date=effective,
        language=language,
    )


def hit(path: str) -> Hit:
    return Hit(
        clause_id=uuid.uuid4(),
        clause_path=path,
        document_version_id=VERSION,
        heading=None,
        text=f"text {path}",
        kind="prose",
        effective_date=None,
        score=1.0,
    )


def claim(path: str) -> Claim:
    return Claim(text="t", citations=[Citation(document_version_id=VERSION, clause_path=path)])


def verdict(value: VerificationVerdict) -> ClaimVerdict:
    return ClaimVerdict(claim_index=0, verdict=value, reason=None, provider="s", model="m")


# --- rendering -------------------------------------------------------------------------------


def test_the_effective_date_is_stated_on_every_answer() -> None:
    retrieval = RetrievalResult(versions=[version()], effective_date_scope=date(2026, 4, 2))

    text = render("변패된 화장품은 판매할 수 없습니다.", retrieval=retrieval)

    assert EFFECTIVE_DATE_NOTICE["ko"].format(date="2026-04-02") in text


def test_a_straddle_is_said_out_loud() -> None:
    retrieval = RetrievalResult(
        versions=[version()],
        effective_date_scope=date(2026, 4, 2),
        straddles_effective_date=True,
    )

    text = render("답변", retrieval=retrieval)

    assert STRADDLE_NOTICE["ko"] in text


def test_the_notice_follows_the_documents_language() -> None:
    retrieval = RetrievalResult(
        versions=[version(language="en")], effective_date_scope=date(2026, 4, 2)
    )

    assert "As of effective date 2026-04-02." in render("answer", retrieval=retrieval)


def test_an_unresolvable_date_adds_no_notice() -> None:
    """ADR-0013: null stays null. A rendered "시행일 None 기준" would be worse than silence."""
    retrieval = RetrievalResult(versions=[version(effective=None)])

    assert render("답변", retrieval=retrieval) == "답변"


# --- confidence ------------------------------------------------------------------------------


def test_a_top_ranked_supported_claim_scores_full_confidence() -> None:
    retrieval = RetrievalResult(hits=[hit("제8조"), hit("제9조")])

    value = score(
        [claim("제8조")], verdicts=[verdict(VerificationVerdict.SUPPORTED)], retrieval=retrieval
    )

    assert value == CONFIDENCE_VERIFICATION_WEIGHT + CONFIDENCE_RETRIEVAL_WEIGHT


def test_citing_a_deeply_ranked_passage_costs_confidence() -> None:
    """A supported claim built from the last hit may still be answering a neighbouring question."""
    retrieval = RetrievalResult(hits=[hit(f"제{n}조") for n in range(1, 9)])

    top = score(
        [claim("제1조")], verdicts=[verdict(VerificationVerdict.SUPPORTED)], retrieval=retrieval
    )
    deep = score(
        [claim("제8조")], verdicts=[verdict(VerificationVerdict.SUPPORTED)], retrieval=retrieval
    )

    assert deep < top


def test_verification_outweighs_retrieval() -> None:
    """Mis-citation survives every structural check, so the verifier's vote has to dominate."""
    retrieval = RetrievalResult(hits=[hit("제8조")])

    unsupported_but_top = score(
        [claim("제8조")], verdicts=[verdict(VerificationVerdict.UNSUPPORTED)], retrieval=retrieval
    )

    assert unsupported_but_top == CONFIDENCE_RETRIEVAL_WEIGHT


def test_confidence_stays_within_range() -> None:
    """The column is CHECK-bounded; a score outside [0, 1] would fail at the insert, not here."""
    retrieval = RetrievalResult(hits=[hit("제8조")])

    value = score(
        [claim("제8조")], verdicts=[verdict(VerificationVerdict.SUPPORTED)], retrieval=retrieval
    )

    assert 0.0 <= value <= 1.0


def test_no_claims_scores_zero() -> None:
    assert score([], verdicts=[], retrieval=RetrievalResult(hits=[hit("제8조")])) == 0.0
