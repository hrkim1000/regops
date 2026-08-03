"""MFDS surfaces — the RSS feed and the 제개정고시등 listing page.

These are change *signals*, not the regulations themselves: they tell us a 고시 was amended so the
법령/행정규칙 connector can go and fetch it. That is why they are modelled as ``DocType.FEED`` and
why their canonicalization matters more than their content does.

The listing page is where the confirmed volatile element lives. Its rows carry ``조회수`` (view
count), which changes on every poll; hashing the row as delivered would report a change every time
and bury the detection-coverage gate in false positives. Dropping it is the whole canonicalization
job for this source, and the test that proves it is the one protecting the gate.
"""

from __future__ import annotations

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import ClassVar

from defusedxml.ElementTree import fromstring as parse_xml

from regops_shared.constants import DocType, DriftSignal

from ..canonicalize import canonical_records, normalize_text
from .base import (
    ArtifactRef,
    AuthorityError,
    FetchedArtifact,
    FetchResult,
    SourceSpec,
    assert_ingestible,
)
from .http import PoliteFetcher

#: RSS item fields worth hashing. Anything else the feed carries is presentation.
_RSS_FIELDS = ("title", "link", "guid", "pubDate", "category")


def parse_rss_date(value: str | None) -> datetime | None:
    """RFC 822 ``pubDate`` → aware datetime. Unparseable stays None rather than becoming our clock.

    Defaulting this to the fetch time would make detection latency equal our own processing time,
    so the ≤24h gate would pass by construction and measure nothing (ADR-0003 decision 5).
    """
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


class _TableRows(HTMLParser):
    """Extract ``<table>`` rows as header→cell dicts.

    Stdlib rather than a parser dependency: this is one table on one page, and the alternative is
    carrying lxml or BeautifulSoup into every service image for it.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.headers: list[str] = []
        self.rows: list[dict[str, str]] = []
        self._cell: list[str] | None = None
        self._row: list[str] = []
        self._in_header = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"}:
            self._cell = []
            self._in_header = tag == "th"

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._cell is not None:
            self._row.append(normalize_text(" ".join(self._cell)))
            self._cell = None
        elif tag == "tr":
            if self._in_header and not self.headers:
                self.headers = self._row
            elif self._row:
                keys = self.headers or [f"col{i}" for i in range(len(self._row))]
                self.rows.append(dict(zip(keys, self._row, strict=False)))
            self._row = []
            self._in_header = False

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)


def extract_table_rows(html: str) -> list[dict[str, str]]:
    parser = _TableRows()
    parser.feed(html)
    parser.close()
    return parser.rows


class _MfdsFeedConnector:
    """Shared fetch shape for both MFDS surfaces."""

    key: ClassVar[str] = ""
    version: ClassVar[str] = "1.0.0"
    key_prefix: ClassVar[str] = "mfds:feed"

    def __init__(self, fetcher: PoliteFetcher | None = None) -> None:
        self._fetcher = fetcher

    def fetch(self, spec: SourceSpec) -> FetchResult:
        assert_ingestible(spec)
        if not spec.url_template:
            raise AuthorityError(
                f"{spec.slug}: source has no url_template", signal=DriftSignal.MISSING_ROOT
            )
        url = spec.url_template
        for key, value in spec.params.items():
            url = url.replace(f"{{{key}}}", str(value))

        fetcher = self._fetcher or PoliteFetcher()
        try:
            response = fetcher.get(url, etag=spec.http_etag, last_modified=spec.http_last_modified)
        finally:
            if self._fetcher is None:
                fetcher.close()

        if response.not_modified:
            return FetchResult(http_status=response.status, not_modified=True)
        if response.status != 200:
            raise AuthorityError(
                f"{spec.slug}: HTTP {response.status}", signal=DriftSignal.MISSING_ROOT
            )

        artifacts = self.parse(response.body, spec=spec)
        return FetchResult(
            http_status=response.status,
            artifacts=artifacts,
            etag=response.etag,
            last_modified=response.last_modified,
            published_at=artifacts[0].published_at if artifacts else None,
        )

    def parse(self, body: bytes, *, spec: SourceSpec) -> tuple[FetchedArtifact, ...]:
        raise NotImplementedError

    def _artifact(
        self,
        *,
        spec: SourceSpec,
        raw: bytes,
        records: list[dict[str, str]],
        published_at: datetime | None,
        content_type: str,
    ) -> tuple[FetchedArtifact, ...]:
        if not records:
            raise AuthorityError(
                f"{spec.slug}: no rows found — the page structure changed, or the query is wrong",
                signal=DriftSignal.ZERO_RECORDS,
            )
        return (
            FetchedArtifact(
                ref=ArtifactRef(
                    canonical_key=f"{self.key_prefix}:{spec.params.get('id', spec.slug)}",
                    title=spec.title,
                    doc_type=DocType.FEED,
                ),
                raw=raw,
                canonical=canonical_records(records),
                content_type=content_type,
                published_at=published_at,
            ),
        )


class MfdsRssConnector(_MfdsFeedConnector):
    """MFDS RSS — notices, legislative notices, amendments."""

    key: ClassVar[str] = "mfds_rss"
    version: ClassVar[str] = "1.0.0"
    key_prefix: ClassVar[str] = "mfds:rss"

    def parse(self, body: bytes, *, spec: SourceSpec) -> tuple[FetchedArtifact, ...]:
        root = parse_xml(body)
        records: list[dict[str, str]] = []
        latest: datetime | None = None

        for item in root.iter("item"):
            record: dict[str, str] = {}
            for field in _RSS_FIELDS:
                element = item.find(field)
                if element is not None and element.text:
                    record[field] = normalize_text(element.text)
            if record:
                records.append(record)
            published = parse_rss_date(record.get("pubDate"))
            if published and (latest is None or published > latest):
                latest = published

        return self._artifact(
            spec=spec,
            raw=body,
            records=records,
            published_at=latest,
            content_type="application/rss+xml",
        )


class MfdsListingConnector(_MfdsFeedConnector):
    """MFDS 제개정고시등 listing — server-rendered HTML with a ``제개정일`` per row.

    ``조회수`` is dropped before hashing. That single exclusion is what keeps a poll of an unchanged
    listing from reading as an amendment.
    """

    key: ClassVar[str] = "mfds_listing"
    version: ClassVar[str] = "1.0.0"
    key_prefix: ClassVar[str] = "mfds:listing"

    def parse(self, body: bytes, *, spec: SourceSpec) -> tuple[FetchedArtifact, ...]:
        rows = extract_table_rows(body.decode("utf-8", errors="replace"))
        return self._artifact(
            spec=spec,
            raw=body,
            records=rows,
            published_at=None,  # the page exposes a per-row date, not a page-level one
            content_type="text/html",
        )


__all__ = [
    "MfdsListingConnector",
    "MfdsRssConnector",
    "extract_table_rows",
    "parse_rss_date",
]
