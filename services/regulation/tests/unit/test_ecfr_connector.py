"""The eCFR connector — two endpoints, and no HTML path at all.

Responses here are the shapes the live API returned on 2026-08-24
(``docs/design/spike-2026-08-24-fda-source-recon.md``), including both 404 bodies: the API fails
honestly and differently for "this node does not exist" and "that date is past the ceiling", and a
connector that could not tell either from a regulation would archive an error page.

No test reaches the network. ``_Fetcher`` records every URL asked for, which is how the
"never HTML" rule (ADR-0018 decision 11) is asserted rather than asserted-in-prose.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from app.connectors import CONNECTOR_KEYS, get_connector
from app.connectors.base import AuthorityError, NonIngestibleSourceError, SourceSpec
from app.connectors.ecfr import ECFRConnector
from app.connectors.http import HttpResponse
from regops_shared.constants import DocType, DriftSignal, SourceTier

# --- doubles -------------------------------------------------------------------------------

VERSIONS = {
    "content_versions": [
        {"identifier": "820.1", "issue_date": "2016-12-31", "removed": False, "substantive": True},
        {"identifier": "820.1", "issue_date": "2026-02-04", "removed": False, "substantive": True},
        {"identifier": "820.10", "issue_date": "2026-02-04", "removed": False, "substantive": True},
        {"identifier": "820.25", "issue_date": "2026-02-04", "removed": True, "substantive": True},
        {"identifier": "820.9", "issue_date": None, "removed": False, "substantive": False},
    ]
}

BODY = (
    b'<?xml version="1.0"?>'
    b'<DIV5 N="820" TYPE="PART"><HEAD>PART 820</HEAD>'
    b'<DIV8 N="820.1" TYPE="SECTION"><HEAD>Scope</HEAD><P>(a) text</P></DIV8>'
    b"</DIV5>"
)

#: The two distinct 404 bodies the API returns. Both are JSON, and neither is a regulation.
NO_CONTENT = b'{"error":"No matching content found."}'
PAST_CEILING = (
    b'{"error":"The requested date 2026-09-30 is past the title\'s most recent issue date '
    b'of 2026-08-20, see https://www.ecfr.gov/api/versioner/v1/titles for details"}'
)


class _Fetcher:
    """Serves canned responses by URL substring and records what was asked for."""

    def __init__(self, *, versions: bytes | None = None, body: bytes = BODY, status: int = 200):
        self._versions = json.dumps(VERSIONS).encode() if versions is None else versions
        self._body = body
        self._status = status
        self.urls: list[str] = []

    def get(self, url: str, *, etag=None, last_modified=None) -> HttpResponse:
        self.urls.append(url)
        if "/versions/" in url:
            return HttpResponse(status=200, body=self._versions, content_type="application/json")
        return HttpResponse(status=self._status, body=self._body, content_type="application/xml")

    def close(self) -> None:  # pragma: no cover - nothing to release
        pass


def _spec(**overrides) -> SourceSpec:
    base = {
        "slug": "fda_samd.regulations.cfr_820",
        "title": "21 CFR Part 820 — Quality Management System Regulation",
        "tier": SourceTier.A,
        "ingestible": True,
        "url_template": None,
        "params": {"title": "21", "part": "820"},
    }
    return SourceSpec(**{**base, **overrides})


# --- registration ---------------------------------------------------------------------------


def test_the_connector_is_reachable_by_key() -> None:
    """A seed row cannot name a connector that does not exist."""
    assert "ecfr_part" in CONNECTOR_KEYS
    assert isinstance(get_connector("ecfr_part"), ECFRConnector)


def test_canonical_key_is_the_adr_form() -> None:
    assert ECFRConnector().canonical_key("21", "820") == "fda:cfr:21-820"


# --- the two endpoints, and only those ------------------------------------------------------


def test_detection_reads_versions_and_the_body_is_fetched_at_that_issue_date() -> None:
    """ADR-0018 decisions 4 and 6: versions states identity, the body is pinned to it."""
    fetcher = _Fetcher()
    result = ECFRConnector(fetcher=fetcher).fetch(_spec())

    assert "/api/versioner/v1/versions/title-21.json?part=820" in fetcher.urls[0]
    # Newest issue_date across the Part's sections — not "current", not the oldest.
    assert "/api/versioner/v1/full/2026-02-04/title-21.xml?part=820" in fetcher.urls[1]
    assert result.artifacts[0].version_label == "2026-02-04"


def test_no_html_url_is_ever_requested() -> None:
    """ADR-0018 decision 11, asserted against the recorded calls rather than trusted."""
    fetcher = _Fetcher()
    ECFRConnector(fetcher=fetcher).fetch(_spec())
    assert fetcher.urls, "the connector made no request at all"
    for url in fetcher.urls:
        assert "/api/versioner/v1/" in url
        assert not url.endswith((".html", "/"))


def test_the_artifact_is_english_and_typed_as_a_regulation() -> None:
    artifact = ECFRConnector(fetcher=_Fetcher()).fetch(_spec()).artifacts[0]
    assert artifact.language == "en"
    assert artifact.ref.doc_type is DocType.REGULATION
    assert artifact.ref.canonical_key == "fda:cfr:21-820"


def test_raw_is_archived_unmodified_and_canonical_is_separate() -> None:
    """``raw`` is what gets cited; ``canonical`` only decides whether anything changed."""
    artifact = ECFRConnector(fetcher=_Fetcher()).fetch(_spec()).artifacts[0]
    assert artifact.raw == BODY
    assert artifact.canonical != artifact.raw or b"  " not in BODY


def test_published_at_is_the_authority_issue_date_not_our_clock() -> None:
    """Defaulting to the fetch clock would make the ≤24h latency gate pass by construction."""
    artifact = ECFRConnector(fetcher=_Fetcher()).fetch(_spec()).artifacts[0]
    assert artifact.published_at == datetime(2026, 2, 4, tzinfo=UTC)


def test_meta_carries_what_the_authority_called_removed() -> None:
    """FDA states removal and states no move, so the diff stage needs the removal list."""
    meta = ECFRConnector(fetcher=_Fetcher()).fetch(_spec()).artifacts[0].meta
    assert meta["issue_date"] == "2026-02-04"
    assert meta["sections_at_issue"] == "3"
    assert meta["removed_sections"] == "820.25"


# --- failing closed -------------------------------------------------------------------------


def test_a_404_body_is_not_mistaken_for_a_regulation() -> None:
    fetcher = _Fetcher(body=NO_CONTENT, status=404)
    with pytest.raises(AuthorityError) as caught:
        ECFRConnector(fetcher=fetcher).fetch(_spec())
    assert caught.value.signal is DriftSignal.MISSING_ROOT


def test_a_200_carrying_a_json_error_is_still_refused() -> None:
    """The quietest failure: transport says fine, and the payload is not a regulation."""
    fetcher = _Fetcher(body=PAST_CEILING, status=200)
    with pytest.raises(AuthorityError) as caught:
        ECFRConnector(fetcher=fetcher).fetch(_spec())
    assert caught.value.signal is DriftSignal.MISSING_ROOT


def test_an_empty_version_history_is_drift_not_an_empty_part() -> None:
    fetcher = _Fetcher(versions=json.dumps({"content_versions": []}).encode())
    with pytest.raises(AuthorityError) as caught:
        ECFRConnector(fetcher=fetcher).fetch(_spec())
    assert caught.value.signal is DriftSignal.ZERO_RECORDS


def test_versions_that_are_not_json_are_drift() -> None:
    fetcher = _Fetcher(versions=b"<html>Access Denied</html>")
    with pytest.raises(AuthorityError):
        ECFRConnector(fetcher=fetcher).fetch(_spec())


def test_a_source_without_title_and_part_is_refused_before_any_request() -> None:
    fetcher = _Fetcher()
    with pytest.raises(AuthorityError):
        ECFRConnector(fetcher=fetcher).fetch(_spec(params={"part": "820"}))
    assert fetcher.urls == []


def test_a_tier_d_source_has_no_fetch_path() -> None:
    """The Tier D refusal is structural, not a policy someone has to remember."""
    fetcher = _Fetcher()
    with pytest.raises(NonIngestibleSourceError):
        ECFRConnector(fetcher=fetcher).fetch(_spec(tier=SourceTier.D, ingestible=False))
    assert fetcher.urls == []


def test_a_304_produces_no_artifact() -> None:
    """The cheapest possible observation: proof it was checked, with nothing transferred."""

    class _NotModified(_Fetcher):
        def get(self, url, *, etag=None, last_modified=None):
            self.urls.append(url)
            if "/versions/" in url:
                return HttpResponse(200, json.dumps(VERSIONS).encode(), "application/json")
            return HttpResponse(304, b"", "application/xml")

    result = ECFRConnector(fetcher=_NotModified()).fetch(_spec())
    assert result.not_modified is True
    assert result.artifacts == ()
