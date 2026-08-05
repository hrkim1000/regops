"""국가법령정보 connector — annex independence, and the three HTTP-200 failure signatures."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from helpers import StubFetcher, fixture_bytes

from app.connectors.base import AuthorityError, SourceSpec
from app.connectors.law_go_kr import (
    AdmRuleConnector,
    LawConnector,
    check_authority_error,
    normalize_annex_no,
    parse_authority_date,
)
from regops_shared.constants import DocType, DriftSignal, SourceTier

ADMRUL_SPEC = SourceSpec(
    slug="mfds_cosmetic.standards.cosmetic_safety_standards",
    title="화장품 안전기준 등에 관한 규정",
    tier=SourceTier.A,
    ingestible=True,
    url_template="https://www.law.go.kr/DRF/lawService.do?OC={OC}&target=admrul&LM={name}",
    params={"name": "화장품 안전기준 등에 관한 규정"},
)

LAW_SPEC = SourceSpec(
    slug="mfds_cosmetic.primary_laws.cosmetics_act",
    title="화장품법",
    tier=SourceTier.A,
    ingestible=True,
    url_template="https://www.law.go.kr/DRF/lawService.do?OC={OC}&target=law&LM={name}",
    params={"name": "화장품법"},
)


def _admrul_artifacts(fixture: str) -> tuple:
    connector = AdmRuleConnector(fetcher=StubFetcher(body=fixture_bytes(fixture)))
    return connector.parse(fixture_bytes(fixture), spec=ADMRUL_SPEC)


# --- annex identity (ADR-0012) -------------------------------------------------


def test_annexes_arrive_inline_as_separate_artifacts() -> None:
    """행정규칙 본문조회 returns <별표단위> with <별표내용> inline, so HWP/PDF extraction is not
    the ingestion route (ADR-0003 decision 10, as revised by the live test)."""
    artifacts = _admrul_artifacts("admrul_cosmetic_safety.xml")

    assert len(artifacts) == 3, "one body + two 별표"
    body, annex1, annex2 = artifacts
    assert body.ref.doc_type is DocType.NOTICE
    assert annex1.ref.doc_type is DocType.ANNEX
    assert annex1.ref.annex_no == "1"
    assert annex2.ref.annex_no == "2"
    assert annex2.ref.parent_canonical_key == body.ref.canonical_key
    assert annex2.ref.canonical_key.endswith("#별표2")


def test_amending_one_annex_leaves_the_body_hash_untouched() -> None:
    """The phase 1.0 acceptance criterion. If the body's hash moved with the annex, the body would
    version too, and 'annexes version independently' would be false in practice."""
    before = _admrul_artifacts("admrul_cosmetic_safety.xml")
    after = _admrul_artifacts("admrul_cosmetic_safety_annex2_amended.xml")

    assert before[0].content_hash == after[0].content_hash, "body must not move"
    assert before[1].content_hash == after[1].content_hash, "별표 1 must not move"
    assert before[2].content_hash != after[2].content_hash, "별표 2 changed and must say so"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("0001", "1"), ("0012", "12"), ("2", "2"), ("1의2", "1의2"), ("0000", "0"), (" 0003 ", "3")],
)
def test_annex_number_matches_how_annexes_are_cited(raw: str, expected: str) -> None:
    """The API zero-pads 별표번호; every human citation and cross-reference says 별표 1.
    Compound numbering such as 1의2 is left verbatim."""
    assert normalize_annex_no(raw) == expected


def test_artifacts_share_the_raw_response() -> None:
    """The raw response is archived unmodified — the annex's evidence is the response it arrived
    in, not a subtree we re-serialized."""
    artifacts = _admrul_artifacts("admrul_cosmetic_safety.xml")
    assert {a.raw for a in artifacts} == {fixture_bytes("admrul_cosmetic_safety.xml")}


def test_annex_file_links_are_recorded_but_do_not_affect_the_hash() -> None:
    """Download links carry sequence numbers that are reissued for an identical file."""
    annex = _admrul_artifacts("admrul_cosmetic_safety.xml")[1]
    assert len(annex.attachments) == 2
    assert {a.file_format for a in annex.attachments} == {"hwp", "pdf"}
    assert b"flDownload" not in annex.canonical


# --- envelope metadata ---------------------------------------------------------


def test_publication_date_comes_from_the_source_not_our_clock() -> None:
    artifacts = _admrul_artifacts("admrul_cosmetic_safety.xml")
    assert artifacts[0].published_at == datetime(2026, 1, 15, tzinfo=UTC)
    assert artifacts[0].version_label == "2026-3"


def test_effective_date_is_not_set_at_fetch_time() -> None:
    """시행일자 is in the envelope, but ``effective_date`` is a parse output (ADR-0003 decision 5).
    1.0 carries it as metadata; 1.1 writes the column."""
    artifacts = _admrul_artifacts("admrul_cosmetic_safety.xml")
    assert artifacts[0].meta["effective_date_raw"] == "20260701"
    assert not hasattr(artifacts[0], "effective_date")


def test_law_response_identity_comes_from_the_response() -> None:
    """Querying by 법령명 does not weaken canonical_key — identity is the 법령ID we got back."""
    connector = LawConnector(fetcher=StubFetcher())
    artifacts = connector.parse(fixture_bytes("law_cosmetics_act.xml"), spec=LAW_SPEC)
    assert artifacts[0].ref.canonical_key == "mfds:law:002015"
    assert artifacts[0].ref.title == "화장품법"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("20260701", datetime(2026, 7, 1, tzinfo=UTC)),
        ("2026-07-01", datetime(2026, 7, 1, tzinfo=UTC)),
        ("2026.07.01", datetime(2026, 7, 1, tzinfo=UTC)),
        ("공포 후 6개월", None),
        ("", None),
        (None, None),
        ("20261301", None),
    ],
)
def test_date_parsing_never_guesses(raw: str | None, expected: datetime | None) -> None:
    assert parse_authority_date(raw) == expected


# --- the three HTTP-200 failure signatures ------------------------------------


def test_unregistered_ip_is_detected_behind_http_200() -> None:
    with pytest.raises(AuthorityError) as exc:
        check_authority_error(fixture_bytes("law_auth_failure.xml"), slug="x")
    assert exc.value.signal is DriftSignal.AUTH_FAILURE


def test_ungranted_scope_is_detected_behind_http_200() -> None:
    body = "<html><body>미신청된 목록/본문에 대한 접근입니다</body></html>".encode()
    with pytest.raises(AuthorityError) as exc:
        check_authority_error(body, slug="x")
    assert exc.value.signal is DriftSignal.AUTH_FAILURE


def test_empty_success_response_is_not_treated_as_a_healthy_fetch() -> None:
    """A malformed query returns ``success`` with totalCnt 0, indistinguishable from 'this law does
    not exist'. Silent, and it would otherwise record a healthy observation."""
    connector = LawConnector(fetcher=StubFetcher())
    with pytest.raises(AuthorityError) as exc:
        connector.parse(fixture_bytes("law_empty_result.xml"), spec=LAW_SPEC)
    assert exc.value.signal is DriftSignal.ZERO_RECORDS


def test_a_valid_response_passes_the_error_check() -> None:
    check_authority_error(fixture_bytes("admrul_cosmetic_safety.xml"), slug="x")


# --- politeness ---------------------------------------------------------------


def test_cache_validators_are_sent_and_a_304_short_circuits() -> None:
    """A 304 is the cheapest possible fetch_observation: proven checked, nothing transferred."""
    stub = StubFetcher(body=b"", status=304)
    spec = SourceSpec(
        slug=ADMRUL_SPEC.slug,
        title=ADMRUL_SPEC.title,
        tier=SourceTier.A,
        ingestible=True,
        url_template="https://example.invalid/x",
        http_etag='W/"abc"',
        http_last_modified="Thu, 15 Jan 2026 00:00:00 GMT",
    )
    result = AdmRuleConnector(fetcher=stub).fetch(spec)

    assert result.not_modified is True
    assert result.artifacts == ()
    assert stub.seen_etag == 'W/"abc"'
    assert stub.seen_last_modified == "Thu, 15 Jan 2026 00:00:00 GMT"


# --- instrument kind comes from the response ----------------------------------


def test_doc_type_is_read_from_the_envelope() -> None:
    """법종구분 states 법률 / 대통령령 / 총리령 outright. Filing 화장품법 시행규칙 as a 법률 is a
    fidelity loss with no excuse, and it is what left DocType.DECREE unreachable."""
    from regops_shared.constants import DocType

    def parse(kind: str) -> DocType:
        body = (
            f"<법령><기본정보><법령ID>1</법령ID><법종구분>{kind}</법종구분></기본정보>"
            "<조문><조문단위><조문내용>x</조문내용></조문단위></조문></법령>"
        ).encode()
        return LawConnector(fetcher=StubFetcher()).parse(body, spec=LAW_SPEC)[0].ref.doc_type

    assert parse("법률") is DocType.LAW
    assert parse("대통령령") is DocType.DECREE
    assert parse("총리령") is DocType.ENFORCEMENT_RULE


def test_admrul_stays_a_notice_when_the_envelope_says_nothing() -> None:
    """행정규칙 carries no 법종구분 — the class default is the answer, not a fallback bug."""
    from regops_shared.constants import DocType

    artifacts = AdmRuleConnector(fetcher=StubFetcher()).parse(
        fixture_bytes("admrul_cosmetic_safety.xml"), spec=ADMRUL_SPEC
    )
    assert artifacts[0].ref.doc_type is DocType.NOTICE
