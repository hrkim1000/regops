"""The discovery sweep, and the credential the authority hands back to us.

Two separate concerns meet in this file because they meet in the same endpoint:

- **Coverage.** A curated catalog caps detection coverage at whatever someone remembered to add
  (ADR-0003 decision 11). The sweep measures that gap — but only if its relevance filter keeps the
  result small enough for a human to read.
- **Credentials.** ``lawSearch.do`` echoes the ``OC`` parameter back inside every row, so this is
  the one endpoint where a key arrives *inbound*. ``redact_url`` does not help there.
"""

from __future__ import annotations

import pytest
from helpers import fixture_bytes

from app.discovery import (
    UpstreamRule,
    cells_for,
    normalize_title,
    parse_index,
)
from regops_shared.constants import MFDS_ORG_CODE


def _rules() -> list[UpstreamRule]:
    return list(parse_index(fixture_bytes("admrul_index.xml")))


# --- the org code -------------------------------------------------------------


def test_org_code_is_a_reviewed_constant_not_an_env_value() -> None:
    """A public identifier belongs in version-controlled code. In a gitignored .env it would be
    invisible to review and every environment would have to rediscover it."""
    assert MFDS_ORG_CODE == "1471000"


# --- parsing ------------------------------------------------------------------


def test_index_rows_parse() -> None:
    rules = _rules()
    assert len(rules) == 5
    by_title = {rule.title: rule for rule in rules}
    cosmetic = by_title["화장품 안전기준 등에 관한 규정"]
    assert cosmetic.admrul_id == "37098"
    assert cosmetic.kind == "고시"
    assert cosmetic.promulgated_on == "20260318"
    assert cosmetic.revision_kind == "일부개정"


def test_upstream_rule_cannot_carry_the_echoed_credential() -> None:
    """The fixture rows all contain 행정규칙상세링크 with an OC parameter. UpstreamRule has no field
    for it — the same structural move as fetch_observations having no request-URL column, and for
    the same reason: source_discovery_runs.details is persisted."""
    assert "OC=" in fixture_bytes("admrul_index.xml").decode("utf-8")

    assert not hasattr(UpstreamRule("1", "t"), "link")
    for rule in _rules():
        for value in rule.as_details().values():
            assert value is None or "OC=" not in value


# --- relevance ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("화장품 안전기준 등에 관한 규정", {"mfds_cosmetic"}),
        ("화장품 색소 종류와 기준 및 시험방법", {"mfds_cosmetic"}),
        ("의료기기 사이버보안 허가·심사 가이드라인", {"mfds_samd"}),
        ("디지털의료제품 허가·심사 규정", {"mfds_samd"}),
        # Out of scope by decision (2026-08-06), and it needs a *negative* rule to get there:
        # 체외진단의료기기 contains 의료기기, so no positive-keyword edit can exclude it.
        ("체외진단의료기기 허가 규정", set()),
        ("범부처 전주기 의료기기 연구개발사업 운영관리규정", set()),
        # "How a programme is run, not what a product must do" — one category, both cells. The
        # 감시원 pair must go together: excluding the device one alone was an asymmetry.
        ("소비자의료기기감시원 운영에 관한 규정", set()),
        ("소비자화장품안전관리감시원 운영 규정", set()),
        ("의료기기위원회 규정", set()),
        ("맞춤형화장품조제관리사 자격시험 운영에 관한 규정", set()),
        # CGMP was ruled out on 2026-08-03 and ruled back **in** on 2026-08-06.
        ("우수화장품 제조 및 품질관리기준", {"mfds_cosmetic"}),
        # A regulation can govern a domain without naming it. Both of these are real MFDS 고시 that
        # the original keyword set could not see (measured 2026-08-06).
        ("의약품등의 타르색소 지정과 기준 및 시험방법", {"mfds_cosmetic"}),
        ("인체적용제품의 위해성평가에 관한 규정", {"mfds_cosmetic", "mfds_samd"}),
        # Out of RegOps scope entirely — 511 MFDS 고시 are mostly these.
        ("HACCP 발전 협의회 운영 규정", set()),
        ("건강기능식품 기능성 원료 및 기준·규격 인정에 관한 규정", set()),
        # 의약외품 is not one of the 8 cells, however close it sits to Cosmetic in Korean law.
        ("의약외품 표준제조기준", set()),
        ("의약품 부작용 피해구제급여 지급 제외 대상 의약품의 지정", set()),
    ],
)
def test_relevance_filter_maps_titles_to_cells(title: str, expected: set[str]) -> None:
    assert cells_for(title) == expected


def test_filter_drops_the_bulk_of_the_authority_list() -> None:
    """Without this, the sweep would report ~500 unmatched 고시 and be muted within a week."""
    in_scope = [rule for rule in _rules() if cells_for(rule.title)]
    assert len(in_scope) == 3
    assert all("식품" not in rule.title for rule in in_scope)


# --- title matching -----------------------------------------------------------


@pytest.mark.parametrize(
    ("catalog", "authority"),
    [
        ("의료기기 허가·신고·심사 등에 관한 규정", "의료기기 허가ㆍ신고ㆍ심사 등에 관한 규정"),
        ("화장품 안전기준 등에 관한 규정", "화장품 안전기준 등에 관한  규정"),
        ("기능성화장품 심사에 관한 규정", "기능성화장품심사에 관한 규정"),
    ],
)
def test_spelling_differences_do_not_read_as_a_coverage_gap(catalog: str, authority: str) -> None:
    """The catalog and the authority differ on 중점 and spacing without naming a different
    instrument. Treating that as 'missing' would manufacture a gap that is not there."""
    assert normalize_title(catalog) == normalize_title(authority)


def test_a_genuinely_different_title_still_differs() -> None:
    assert normalize_title("화장품 안전기준 등에 관한 규정") != normalize_title(
        "화장품 색소 종류와 기준 및 시험방법"
    )
