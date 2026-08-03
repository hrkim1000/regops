"""MFDS RSS and listing — change *signals*, not the regulations themselves."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from helpers import StubFetcher, fixture_bytes, fixture_text

from app.connectors.base import AuthorityError, SourceSpec
from app.connectors.mfds import (
    MfdsListingConnector,
    MfdsRssConnector,
    extract_table_rows,
    parse_rss_date,
)
from regops_shared.constants import DocType, DriftSignal, SourceTier

RSS_SPEC = SourceSpec(
    slug="mfds_cosmetic.safety.mfds_rss",
    title="MFDS RSS",
    tier=SourceTier.B,
    ingestible=True,
    url_template="https://www.mfds.go.kr/www/rss/list.do",
)

LISTING_SPEC = SourceSpec(
    slug="mfds_cosmetic.safety.mfds_amendment_listing",
    title="MFDS 제개정고시등",
    tier=SourceTier.B,
    ingestible=True,
    url_template="https://www.mfds.go.kr/brd/m_207/list.do",
)


def test_rss_items_become_one_feed_artifact() -> None:
    connector = MfdsRssConnector(fetcher=StubFetcher())
    artifacts = connector.parse(fixture_bytes("mfds_rss.xml"), spec=RSS_SPEC)

    assert len(artifacts) == 1
    assert artifacts[0].ref.doc_type is DocType.FEED
    assert artifacts[0].published_at == datetime(2026, 1, 15, 0, 0, tzinfo=UTC)


def test_rss_publication_date_is_the_newest_item() -> None:
    """Detection latency is measured from the authority's publication, so the feed's own signal is
    the most recent thing it announced."""
    connector = MfdsRssConnector(fetcher=StubFetcher())
    artifacts = connector.parse(fixture_bytes("mfds_rss.xml"), spec=RSS_SPEC)
    assert artifacts[0].published_at is not None
    assert artifacts[0].published_at > datetime(2026, 1, 9, tzinfo=UTC)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Thu, 15 Jan 2026 09:00:00 +0900", datetime(2026, 1, 15, 0, 0, tzinfo=UTC)),
        ("not a date", None),
        ("", None),
        (None, None),
    ],
)
def test_rss_date_parsing_never_falls_back_to_our_clock(
    raw: str | None, expected: datetime | None
) -> None:
    assert parse_rss_date(raw) == expected


def test_listing_rows_are_extracted_with_headers() -> None:
    rows = extract_table_rows(fixture_text("mfds_listing.html"))
    assert len(rows) == 3
    assert rows[0]["제개정일"] == "2026-01-15"
    assert rows[0]["조회수"] == "1204"


def test_listing_becomes_a_feed_artifact() -> None:
    connector = MfdsListingConnector(fetcher=StubFetcher())
    artifacts = connector.parse(fixture_bytes("mfds_listing.html"), spec=LISTING_SPEC)
    assert len(artifacts) == 1
    assert artifacts[0].content_type == "text/html"
    # The page exposes a per-row 제개정일, not a page-level publication timestamp. Null rather
    # than our fetch clock: latency for this source is unmeasurable, not zero.
    assert artifacts[0].published_at is None


def test_empty_listing_fails_closed_as_drift() -> None:
    """A redesign that empties the table is an operator alert, never a change event."""
    connector = MfdsListingConnector(fetcher=StubFetcher())
    with pytest.raises(AuthorityError) as exc:
        connector.parse(b"<html><body><p>maintenance</p></body></html>", spec=LISTING_SPEC)
    assert exc.value.signal is DriftSignal.ZERO_RECORDS
