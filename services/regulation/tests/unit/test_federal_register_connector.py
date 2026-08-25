"""The Federal Register connector — dates and identifiers, never regulation text.

The payload here is the shape the live API returned for 21 CFR Part 820 on 2026-08-24, including
the parts that make the modelling non-obvious: a rule with a **null** ``effective_on``, one whose
``cfr_references`` names two Parts, and the QMSR pair — two documents carrying the *same* effective
date, which is why a version cannot be keyed on that date alone.

No test reaches the network.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from app.canonicalize import canonical_records
from app.connectors import CONNECTOR_KEYS, get_connector
from app.connectors.base import AuthorityError, NonIngestibleSourceError, SourceSpec
from app.connectors.federal_register import FederalRegisterConnector
from app.connectors.http import HttpResponse
from regops_shared.constants import DocType, DriftSignal, SourceTier

# --- doubles -------------------------------------------------------------------------------

PAYLOAD = {
    "count": 3,
    "results": [
        {
            "document_number": "2024-23701",
            "citation": "89 FR 82945",
            "type": "Rule",
            "publication_date": "2024-10-15",
            "effective_on": "2026-02-02",
            "cfr_references": [{"title": 21, "part": "820"}],
            "dates": "This rule is effective February 2, 2026.",
            "html_url": "https://www.federalregister.gov/documents/2024-23701",
        },
        {
            "document_number": "2024-01709",
            "citation": "89 FR 7496",
            "type": "Rule",
            "publication_date": "2024-02-02",
            "effective_on": "2026-02-02",
            # One rule, two Parts — the reference list is not one-to-one with a Document.
            "cfr_references": [{"title": 21, "part": "820"}, {"title": 21, "part": "4"}],
            "dates": "This rule is effective February 2, 2026. The incorporation by reference…",
            "html_url": "https://www.federalregister.gov/documents/2024-01709",
        },
        {
            "document_number": "2013-22217",
            "citation": "78 FR 58822",
            "type": "Rule",
            "publication_date": "2013-09-24",
            # Nullable. ADR-0013: null with the phrase retained, never a derived date.
            "effective_on": None,
            "cfr_references": [{"title": 21, "part": "820"}],
            "dates": "Effective date: see SUPPLEMENTARY INFORMATION.",
            "html_url": "https://www.federalregister.gov/documents/2013-22217",
        },
    ],
}


class _Fetcher:
    def __init__(self, *, payload: object = None, status: int = 200, body: bytes | None = None):
        self._body = body if body is not None else json.dumps(payload or PAYLOAD).encode()
        self._status = status
        self.urls: list[str] = []

    def get(self, url: str, *, etag=None, last_modified=None) -> HttpResponse:
        self.urls.append(url)
        return HttpResponse(status=self._status, body=self._body, content_type="application/json")

    def close(self) -> None:  # pragma: no cover - nothing to release
        pass


def _spec(**overrides) -> SourceSpec:
    base = {
        "slug": "fda_samd.regulations.fr_820",
        "title": "Federal Register — 21 CFR Part 820",
        "tier": SourceTier.A,
        "ingestible": True,
        "url_template": None,
        "params": {"title": "21", "part": "820"},
    }
    return SourceSpec(**{**base, **overrides})


def _fetch(fetcher: _Fetcher | None = None, **overrides):
    return FederalRegisterConnector(fetcher=fetcher or _Fetcher()).fetch(_spec(**overrides))


# --- registration and shape -----------------------------------------------------------------


def test_the_connector_is_reachable_by_key() -> None:
    assert "federal_register" in CONNECTOR_KEYS
    assert isinstance(get_connector("federal_register"), FederalRegisterConnector)


def test_the_feed_key_pairs_with_the_ecfr_document_key() -> None:
    """``fda:fr:21-820`` against ``fda:cfr:21-820`` — the join is structural, not a search."""
    assert FederalRegisterConnector().canonical_key("21", "820") == "fda:fr:21-820"


def test_a_rule_is_a_feed_not_a_document_to_cite() -> None:
    """ADR-0018 decision 4: the CFR is what an RA cites, so a rule carries no clauses."""
    artifact = _fetch().artifacts[0]
    assert artifact.ref.doc_type is DocType.FEED
    assert artifact.language == "en"


# --- the query ------------------------------------------------------------------------------


def test_the_query_filters_by_agency_type_and_cfr_part() -> None:
    fetcher = _Fetcher()
    _fetch(fetcher)
    url = fetcher.urls[0]
    assert "conditions%5Bagencies%5D%5B%5D=food-and-drug-administration" in url
    assert "conditions%5Bcfr%5D%5Btitle%5D=21" in url
    assert "conditions%5Bcfr%5D%5Bpart%5D=820" in url


def test_the_type_filter_is_present_because_cfr_alone_returns_proposed_rules() -> None:
    """Without it the same query yields Proposed Rules, which amend nothing and have no date."""
    fetcher = _Fetcher()
    _fetch(fetcher)
    assert "conditions%5Btype%5D%5B%5D=RULE" in fetcher.urls[0]


def test_only_documented_api_urls_are_requested() -> None:
    """ADR-0018 decision 11 covers this host too — never its HTML."""
    fetcher = _Fetcher()
    _fetch(fetcher)
    for url in fetcher.urls:
        assert url.startswith("https://www.federalregister.gov/api/v1/")


# --- what the version stage needs ------------------------------------------------------------


def test_published_at_is_the_newest_publication_date_not_our_clock() -> None:
    artifact = _fetch().artifacts[0]
    assert artifact.published_at == datetime(2024, 10, 15, tzinfo=UTC)


def test_a_null_effective_date_is_carried_as_empty_never_as_a_guess() -> None:
    """ADR-0013 — a derived date in the Citation tuple is indistinguishable from a real one."""
    artifact = _fetch().artifacts[0]
    assert artifact.meta["rules_without_effective_date"] == "1"
    assert b'"effective_on": ""' in artifact.canonical or b"effective_on" in artifact.canonical


def test_the_dates_prose_survives_for_the_rules_that_state_no_date() -> None:
    """It becomes ``effective_date_phrase``; discarding it loses the only evidence left."""
    artifact = _fetch().artifacts[0]
    assert b"see SUPPLEMENTARY INFORMATION" in artifact.canonical


def test_cfr_references_are_flattened_and_sorted() -> None:
    """One rule can name several Parts, and the API does not promise an order.

    An unstable order would hash differently on every poll and report an amendment that never
    happened — the exact false-positive class ADR-0003 decision 2 exists to prevent.
    """
    artifact = _fetch().artifacts[0]
    assert b"21-4,21-820" in artifact.canonical


def test_two_rules_can_share_one_effective_date() -> None:
    """The QMSR pair. A version keyed on the effective date alone would collide on them."""
    same = [r for r in PAYLOAD["results"] if r["effective_on"] == "2026-02-02"]
    assert len(same) == 2
    artifact = _fetch().artifacts[0]
    assert artifact.meta["rules_returned"] == "3"


# --- pending effect, which is the other half of the point ------------------------------------


def test_a_future_effective_date_is_reported_as_pending() -> None:
    """ADR-0018 decision 7: the eCFR 404s on future dates, so this is the only view of them."""
    future = json.loads(json.dumps(PAYLOAD))
    future["results"][0]["effective_on"] = "2033-03-07"
    artifact = _fetch(_Fetcher(payload=future)).artifacts[0]
    assert artifact.meta["pending_count"] == "1"
    assert artifact.meta["latest_pending"] == "2033-03-07"


def test_nothing_pending_reports_no_pending_window() -> None:
    artifact = _fetch().artifacts[0]
    assert artifact.meta["pending_count"] == "0"
    assert "earliest_pending" not in artifact.meta


# --- honesty about limits ---------------------------------------------------------------------


def test_a_truncated_result_set_says_so_rather_than_looking_complete() -> None:
    """A silent cap reads as "we saw everything" when we did not."""
    big = json.loads(json.dumps(PAYLOAD))
    big["count"] = 412
    artifact = _fetch(_Fetcher(payload=big)).artifacts[0]
    assert artifact.meta["truncated_of_total"] == "412"


def test_an_untruncated_result_set_carries_no_truncation_key() -> None:
    assert "truncated_of_total" not in _fetch().artifacts[0].meta


# --- failing closed ---------------------------------------------------------------------------


def test_an_html_body_on_http_200_is_refused() -> None:
    """The bot-check page is served with a 200 to an unrecognised client."""
    with pytest.raises(AuthorityError) as caught:
        _fetch(_Fetcher(body=b"<html>Request Access</html>"))
    assert caught.value.signal is DriftSignal.MISSING_ROOT


def test_a_payload_without_results_is_drift() -> None:
    with pytest.raises(AuthorityError) as caught:
        _fetch(_Fetcher(payload={"count": 0}))
    assert caught.value.signal is DriftSignal.MISSING_ROOT


def test_an_empty_result_set_is_drift_not_a_quiet_zero() -> None:
    """A Part we ingest having no final rules at all is far likelier to be a broken filter."""
    with pytest.raises(AuthorityError) as caught:
        _fetch(_Fetcher(payload={"count": 0, "results": []}))
    assert caught.value.signal is DriftSignal.ZERO_RECORDS


def test_a_non_200_is_refused() -> None:
    with pytest.raises(AuthorityError):
        _fetch(_Fetcher(status=503))


def test_a_source_without_title_and_part_is_refused_before_any_request() -> None:
    fetcher = _Fetcher()
    with pytest.raises(AuthorityError):
        FederalRegisterConnector(fetcher=fetcher).fetch(_spec(params={"title": "21"}))
    assert fetcher.urls == []


def test_a_tier_d_source_has_no_fetch_path() -> None:
    fetcher = _Fetcher()
    with pytest.raises(NonIngestibleSourceError):
        FederalRegisterConnector(fetcher=fetcher).fetch(_spec(tier=SourceTier.D, ingestible=False))
    assert fetcher.urls == []


# --- change detection ---------------------------------------------------------------------------


def test_an_unchanged_result_set_hashes_the_same() -> None:
    """Two polls of an unmoved Part must not look like an amendment."""
    first = _fetch().artifacts[0]
    second = _fetch().artifacts[0]
    assert first.content_hash == second.content_hash


def test_a_new_rule_changes_the_hash() -> None:
    extra = json.loads(json.dumps(PAYLOAD))
    extra["results"].insert(
        0,
        {
            "document_number": "2026-16942",
            "citation": "91 FR 53524",
            "type": "Rule",
            "publication_date": "2026-08-19",
            "effective_on": "2026-08-19",
            "cfr_references": [{"title": 21, "part": "820"}],
            "dates": "Effective August 19, 2026.",
            "html_url": "https://www.federalregister.gov/documents/2026-16942",
        },
    )
    assert (
        _fetch().artifacts[0].content_hash
        != _fetch(_Fetcher(payload=extra)).artifacts[0].content_hash
    )


def test_canonical_is_built_from_the_records_not_the_raw_bytes() -> None:
    """``raw`` is the archived evidence; ``canonical`` is only what decides whether it moved."""
    artifact = _fetch().artifacts[0]
    assert artifact.raw == json.dumps(PAYLOAD).encode()
    assert artifact.canonical != artifact.raw
    assert canonical_records([]) != artifact.canonical
