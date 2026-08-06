"""The 시행예정 connector — MST as version identity, and the failure modes around it.

Every shape below was probed against the live API on 2026-08-06 and is recorded in
[ADR-0016](../../../../docs/design/ADR-0016-pending-effect-versions.md).
"""

from __future__ import annotations

import pytest

from app.connectors import AuthorityError, SourceSpec, get_connector
from app.connectors.law_go_kr import PendingLawConnector
from regops_shared.constants import DocType, DriftSignal, SourceTier

#: The live shape: MST 282015 appears three times with different 시행일자, the query also returns
#: 화장품법 시행령 (a different instrument), and one row is 현행 rather than 시행예정.
EFLAW_LIST = """<?xml version="1.0" encoding="UTF-8"?>
<LawSearch>
  <target>eflaw</target><totalCnt>6</totalCnt>
  <law><법령ID>002015</법령ID><법령명한글>화장품법</법령명한글>
    <법령일련번호>282015</법령일련번호><현행연혁코드>시행예정</현행연혁코드>
    <공포일자>20251230</공포일자><시행일자>20290101</시행일자></law>
  <law><법령ID>002015</법령ID><법령명한글>화장품법</법령명한글>
    <법령일련번호>282015</법령일련번호><현행연혁코드>시행예정</현행연혁코드>
    <공포일자>20251230</공포일자><시행일자>20280101</시행일자></law>
  <law><법령ID>002015</법령ID><법령명한글>화장품법</법령명한글>
    <법령일련번호>282015</법령일련번호><현행연혁코드>시행예정</현행연혁코드>
    <공포일자>20251230</공포일자><시행일자>20261231</시행일자></law>
  <law><법령ID>002015</법령ID><법령명한글>화장품법</법령명한글>
    <법령일련번호>285681</법령일련번호><현행연혁코드>시행예정</현행연혁코드>
    <공포일자>20260428</공포일자><시행일자>20270429</시행일자></law>
  <law><법령ID>002015</법령ID><법령명한글>화장품법</법령명한글>
    <법령일련번호>270323</법령일련번호><현행연혁코드>현행</현행연혁코드>
    <공포일자>20250401</공포일자><시행일자>20260402</시행일자></law>
  <law><법령ID>002015</법령ID><법령명한글>화장품법</법령명한글>
    <법령일련번호>268901</법령일련번호><현행연혁코드>연혁</현행연혁코드>
    <공포일자>20250131</공포일자><시행일자>20250801</시행일자></law>
  <law><법령ID>005668</법령ID><법령명한글>화장품법 시행령</법령명한글>
    <법령일련번호>299999</법령일련번호><현행연혁코드>시행예정</현행연혁코드>
    <공포일자>20260101</공포일자><시행일자>20270101</시행일자></law>
</LawSearch>
"""

BODY = """<?xml version="1.0" encoding="UTF-8"?>
<법령>
  <기본정보><법령ID>002015</법령ID><법종구분>법률</법종구분>
    <법령명_한글>화장품법</법령명_한글><공포일자>20251230</공포일자>
    <공포번호>21302</공포번호><시행일자>20261231</시행일자></기본정보>
  <조문><조문단위 조문키="0001001"><조문번호>1</조문번호><조문여부>조문</조문여부>
    <조문시행일자>20261231</조문시행일자>
    <조문내용>제1조(목적) 목적.</조문내용></조문단위></조문>
</법령>
"""

#: What ``lawService.do?target=eflaw`` actually returns — HTTP 500 with an XHTML page.
ERROR_PAGE = b'<!DOCTYPE html><html xmlns="http://www.w3.org/1999/xhtml"><body>500</body></html>'


class _Response:
    def __init__(self, body: bytes, status: int = 200) -> None:
        self.body = body
        self.status = status
        self.not_modified = False
        self.etag = None
        self.last_modified = None


class _Fetcher:
    """Serves the list first, then a body per MST, and records what was asked for."""

    def __init__(self, *, body: bytes = BODY.encode(), status: int = 200) -> None:
        self.calls: list[str] = []
        self._body = body
        self._status = status

    def get(self, url: str, **_: object) -> _Response:
        self.calls.append(url)
        if "lawSearch.do" in url:
            return _Response(EFLAW_LIST.encode())
        return _Response(self._body, self._status)

    def close(self) -> None:  # pragma: no cover - interface completeness
        pass


@pytest.fixture(autouse=True)
def _credential(monkeypatch: pytest.MonkeyPatch):
    """Supply a throwaway key so the suite does not depend on the ambient environment.

    ``_body_url`` resolves the ``{OC}`` placeholder through :func:`resolve_url`, which raises when
    settings carry no credential — correct in production, and it made these tests pass inside the
    container (where ``.env`` is loaded) and fail on the host. A unit test must not care either way.
    """
    from regops_shared import settings as settings_module

    monkeypatch.setenv("LAW_GO_KR_OC", "unit-test-key")
    settings_module.get_settings.cache_clear()
    yield
    settings_module.get_settings.cache_clear()


def _spec(**overrides: object) -> SourceSpec:
    base = {
        "slug": "mfds_cosmetic.primary_laws.cosmetics_act_pending",
        "title": "화장품법 (시행예정)",
        "tier": SourceTier.A,
        "ingestible": True,
        "url_template": (
            "https://www.law.go.kr/DRF/lawSearch.do"
            "?OC={OC}&target=eflaw&type=XML&display=100&query={name}"
        ),
        "params": {"name": "화장품법"},
    }
    base.update(overrides)
    return SourceSpec(**base)  # type: ignore[arg-type]


def test_the_connector_is_registered() -> None:
    assert isinstance(get_connector("law_go_kr_eflaw"), PendingLawConnector)


def test_one_mst_carrying_three_effective_dates_yields_one_body_fetch() -> None:
    """**ADR-0016 decision 1.** MST 282015 appears three times in the list; keying versions on
    시행일자 would triplicate identical text and emit two phantom amendments."""
    fetcher = _Fetcher()
    result = PendingLawConnector(fetcher=fetcher).fetch(_spec())

    body_calls = [url for url in fetcher.calls if "lawService.do" in url]
    assert len(body_calls) == 2  # MST 282015 and 285681 — not five rows
    assert "MST=282015" in body_calls[0]
    assert len(result.artifacts) == 2


def test_history_and_current_rows_are_excluded() -> None:
    """연혁 would supply diff baselines we did not archive ourselves, which the citation contract
    does not accept (ADR-0003 decision 12); 현행 is already covered by the other source."""
    fetcher = _Fetcher()
    PendingLawConnector(fetcher=fetcher).fetch(_spec())
    body_calls = " ".join(url for url in fetcher.calls if "lawService.do" in url)

    assert "MST=270323" not in body_calls  # 현행
    assert "MST=268901" not in body_calls  # 연혁


def test_a_different_instrument_in_the_same_result_is_ignored() -> None:
    """The endpoint takes a name *query*, so a search for 화장품법 also returns 화장품법 시행령 —
    100 rows, live. Exact-match on 법령명한글 is what keeps them apart."""
    fetcher = _Fetcher()
    PendingLawConnector(fetcher=fetcher).fetch(_spec())
    assert "MST=299999" not in " ".join(fetcher.calls)


def test_the_body_is_fetched_through_target_law_never_target_eflaw() -> None:
    """``target=eflaw`` has no 본문조회 endpoint (ADR-0016 decision 2)."""
    fetcher = _Fetcher()
    PendingLawConnector(fetcher=fetcher).fetch(_spec())
    body_calls = [url for url in fetcher.calls if "lawService.do" in url]

    assert all("target=law&" in url for url in body_calls)
    assert not any("target=eflaw" in url for url in body_calls)


def test_efyd_is_never_sent() -> None:
    """The parameter is silently ignored and returns the wrong snapshot, which is worse than an
    error — the caller would believe it had the 2028 text."""
    fetcher = _Fetcher()
    PendingLawConnector(fetcher=fetcher).fetch(_spec())
    assert not any("efYd" in url for url in fetcher.calls)


def test_the_pending_version_attaches_to_the_same_document_as_current() -> None:
    """Both resolve to 법령ID 002015, so 현행 and 시행예정 are versions of one Document — which is
    what lets the diff stage compare them at all."""
    result = PendingLawConnector(fetcher=_Fetcher()).fetch(_spec())
    assert result.artifacts[0].ref.canonical_key == "mfds:law:002015"
    assert result.artifacts[0].ref.doc_type is DocType.LAW


def test_an_xhtml_error_page_is_refused_rather_than_archived() -> None:
    """Archiving the 500 page would create a version whose regulation text is an error message."""
    connector = PendingLawConnector(fetcher=_Fetcher(body=ERROR_PAGE))
    with pytest.raises(AuthorityError) as excinfo:
        connector.fetch(_spec())
    assert excinfo.value.signal is DriftSignal.MISSING_ROOT


def test_a_non_200_body_is_refused() -> None:
    connector = PendingLawConnector(fetcher=_Fetcher(status=500))
    with pytest.raises(AuthorityError):
        connector.fetch(_spec())


def test_a_source_without_a_name_param_fails_loudly() -> None:
    with pytest.raises(AuthorityError):
        PendingLawConnector(fetcher=_Fetcher()).fetch(_spec(params={}))


def test_tier_d_is_still_unfetchable() -> None:
    from app.connectors import NonIngestibleSourceError

    with pytest.raises(NonIngestibleSourceError):
        PendingLawConnector(fetcher=_Fetcher()).fetch(_spec(tier=SourceTier.D))
