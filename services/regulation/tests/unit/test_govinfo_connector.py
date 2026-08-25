"""The govinfo connector — the FD&C Act, and a credential that must never reach a URL.

Responses here are the shapes api.govinfo.gov returned on 2026-08-25
(``docs/design/spike-2026-08-24-fda-source-recon.md``). No test reaches the network. ``_Fetcher``
records every URL *and* every header set, which is how both invariants are asserted rather than
asserted-in-prose: the key travels in ``X-Api-Key``, and no URL ever carries it.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from app.connectors import CONNECTOR_KEYS, get_connector
from app.connectors.base import AuthorityError, NonIngestibleSourceError, SourceSpec
from app.connectors.govinfo import GovInfoUSCodeConnector
from app.connectors.http import HttpResponse
from regops_shared.constants import DocType, DriftSignal, SourceTier

#: A credential shape, not a credential. Never a real key, in code, tests or fixtures.
FAKE_KEY = "test-key-not-a-real-credential"

#: The newest edition the fake publishes. Relative to *now* rather than a literal year, so this
#: suite does not start failing on a calendar boundary — the connector derives its candidate years
#: from the clock, and a fixture pinned to 2024 would silently fall out of the lookback window.
EDITION_YEAR = datetime.now(tz=UTC).year - 1
EDITION = f"USCODE-{EDITION_YEAR}-title21"

SUMMARY = json.dumps(
    {
        "title": "FOOD AND DRUGS",
        "dateIssued": f"{EDITION_YEAR}-12-31",
        "packageId": EDITION,
    }
).encode()

GRANULE = (
    b'<html><body><p class="subchapter-head">SUBCHAPTER V - DRUGS AND DEVICES</p>'
    b'<h3 class="section-head">&sect;351. Adulterated drugs and devices</h3>'
    b'<p class="statutory-body">(a) Poisonous ingredients</p>'
    b'<p class="source-credit">(June 25, 1938, ch. 675, &sect;501, 52 Stat. 1049.)</p>'
    b"</body></html>"
)


class _Fetcher:
    """Serves canned responses by URL substring and records URLs and headers."""

    def __init__(self, *, published: tuple[int, ...] = (EDITION_YEAR,), granule: bytes = GRANULE):
        self._published = published
        self._granule = granule
        self.urls: list[str] = []
        self.headers: list[dict[str, str]] = []

    def get(self, url, *, etag=None, last_modified=None, extra_headers=None) -> HttpResponse:
        self.urls.append(url)
        self.headers.append(dict(extra_headers or {}))
        if "/summary" in url:
            # Exactly as the live API behaves: an edition that has not been published 404s.
            if not any(f"USCODE-{year}-" in url for year in self._published):
                return HttpResponse(status=404, body=b"{}", content_type="application/json")
            return HttpResponse(status=200, body=SUMMARY, content_type="application/json")
        return HttpResponse(status=200, body=self._granule, content_type="text/html")

    def close(self) -> None:  # pragma: no cover - nothing to release
        pass


def _spec(**overrides) -> SourceSpec:
    base = {
        "slug": "fda_samd.primary_laws.usc_21_chap9",
        "title": "21 U.S.C. chapter 9 — Federal Food, Drug, and Cosmetic Act",
        "tier": SourceTier.A,
        "ingestible": True,
        "url_template": None,
        "params": {"title": "21", "chapter": "9"},
    }
    return SourceSpec(**{**base, **overrides})


@pytest.fixture
def keyed(monkeypatch: pytest.MonkeyPatch):
    """A configured key, without touching a real one."""
    from app.connectors import govinfo

    monkeypatch.setattr(govinfo, "_auth_headers", lambda slug: {"X-Api-Key": FAKE_KEY})


# --- registration ---------------------------------------------------------------------------


def test_the_connector_is_reachable_by_key() -> None:
    assert "govinfo_uscode" in CONNECTOR_KEYS
    assert isinstance(get_connector("govinfo_uscode"), GovInfoUSCodeConnector)


def test_canonical_key_is_the_adr_form() -> None:
    """One Document for the Act, claimed by both FDA cells — ADR-0018 decision 12."""
    assert GovInfoUSCodeConnector().canonical_key("21", "9") == "fda:usc:21-9"


# --- the credential -------------------------------------------------------------------------


def test_the_key_travels_in_a_header_and_never_in_a_url(keyed: None) -> None:
    """api.govinfo.gov accepts ``api_key`` as a query parameter, and we do not use it.

    A URL is written to ``sources``, echoed into logs and quoted back in errors. This assertion is
    what stops a future "just add it to the query string" from leaking a live credential into all
    three.
    """
    fetcher = _Fetcher()
    GovInfoUSCodeConnector(fetcher=fetcher).fetch(_spec())

    assert fetcher.urls, "no request was made"
    for url in fetcher.urls:
        assert FAKE_KEY not in url
        assert "api_key" not in url
    assert all(headers.get("X-Api-Key") == FAKE_KEY for headers in fetcher.headers)


def test_an_unconfigured_key_fails_rather_than_falling_back(monkeypatch) -> None:
    """Anonymous access is 401, not a reduced quota, so there is nothing to degrade to."""
    from regops_shared.settings import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "govinfo_api_key", None)
    get_settings.cache_clear()
    monkeypatch.setattr("app.connectors.govinfo.get_settings", lambda: settings)

    with pytest.raises(AuthorityError) as caught:
        GovInfoUSCodeConnector(fetcher=_Fetcher()).fetch(_spec())
    assert caught.value.signal is DriftSignal.MISSING_ROOT


# --- the edition ----------------------------------------------------------------------------


def test_the_version_label_is_the_authority_s_package_id(keyed: None) -> None:
    """ADR-0018 decision 12: the version is the annual edition, named as the publisher names it."""
    result = GovInfoUSCodeConnector(fetcher=_Fetcher()).fetch(_spec())
    artifact = result.artifacts[0]

    assert artifact.version_label == EDITION
    assert artifact.ref.doc_type is DocType.CODIFIED_STATUTE
    assert artifact.ref.canonical_key == "fda:usc:21-9"
    assert artifact.published_at is not None
    assert artifact.published_at.date().isoformat() == f"{EDITION_YEAR}-12-31"


def test_a_year_that_does_not_exist_yet_walks_back(keyed: None) -> None:
    """The edition year is a candidate from our clock; the publisher decides whether it exists.

    Early in a calendar year the newest edition is the previous one, and a 404 is the ordinary
    answer rather than an error.
    """
    this_year = datetime.now(tz=UTC).year
    result = GovInfoUSCodeConnector(fetcher=(fetcher := _Fetcher())).fetch(_spec())

    assert f"USCODE-{this_year}-title21" in fetcher.urls[0], "the current year is tried first"
    assert result.artifacts[0].version_label == EDITION, "and the published edition is what lands"


def test_no_edition_at_all_is_drift(keyed: None) -> None:
    fetcher = _Fetcher(published=())
    with pytest.raises(AuthorityError) as caught:
        GovInfoUSCodeConnector(fetcher=fetcher).fetch(_spec())
    assert caught.value.signal is DriftSignal.ZERO_RECORDS


# --- fail-closed ----------------------------------------------------------------------------


def test_a_body_with_no_section_head_never_becomes_a_version(keyed: None) -> None:
    """The chapter carries 309 of them. A body without one is a redesign or an error page, and
    neither is a statute — fail before a version is written (ADR-0003 decision 6)."""
    fetcher = _Fetcher(granule=b"<html><body><p>Service unavailable</p></body></html>")
    with pytest.raises(AuthorityError) as caught:
        GovInfoUSCodeConnector(fetcher=fetcher).fetch(_spec())
    assert caught.value.signal is DriftSignal.MISSING_ROOT


def test_a_non_ingestible_source_is_refused(keyed: None) -> None:
    with pytest.raises(NonIngestibleSourceError):
        GovInfoUSCodeConnector(fetcher=_Fetcher()).fetch(_spec(ingestible=False))


def test_params_must_name_the_chapter(keyed: None) -> None:
    with pytest.raises(AuthorityError):
        GovInfoUSCodeConnector(fetcher=_Fetcher()).fetch(_spec(params={"title": "21"}))
