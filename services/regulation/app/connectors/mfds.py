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
    """Extract ``<table>`` rows as header to cell dicts.

    Stdlib rather than a parser dependency: this is one table on one page, and the alternative is
    carrying lxml or BeautifulSoup into every service image for it.

    **It honours three standard attributes, and that is the whole of the "second authority"
    support.** The FDA Recognized Consensus Standards table uses none of the markup the MFDS
    listings do — there is no ``<th>`` anywhere in it — and the first reading of that was that a
    bespoke rule was needed. The markup says otherwise:

    ``scope="col"``
        The FDA header row is ``<td>`` throughout, but every cell carries ``scope="col"`` — the
        attribute that makes a cell a column header. Honouring it is reading HTML correctly, not
        accommodating one authority.

    ``rowspan``
        One recognition can cover several standard designations, and the table says so the way any
        table does: the shared cells carry ``rowspan="2"`` and the continuation row supplies only
        the columns that differ. Carried down, that continuation becomes a full row; ignored, its
        three cells line up against the first three headers and file a developing organization as a
        date of entry.

    ``colspan``
        A single cell spanning the full width is a banner — the FDA table opens with a *New Search /
        Export to Excel* bar at ``colspan="7"``. Skipping it needs no list of chrome phrases that
        someone would have to maintain.

    None of this is keyed on an authority, and none of it touches the MFDS path: those pages use
    ``<th>`` and carry no ``rowspan``, ``colspan`` or ``scope`` at all.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.headers: list[str] = []
        self.rows: list[dict[str, str]] = []
        self._cell: list[str] | None = None
        #: (text, colspan, rowspan) for each cell of the row being read.
        self._row: list[tuple[str, int, int]] = []
        self._colspan = 1
        self._rowspan = 1
        self._header_cell = False
        self._in_header = False
        #: column index -> (text, rows still to fill) carried down from a ``rowspan`` above.
        self._pending: dict[int, tuple[str, int]] = {}

    @staticmethod
    def _span(attrs: list[tuple[str, str | None]], name: str) -> int:
        """A span attribute, floored at 1. A malformed value is ignored rather than trusted."""
        for key, value in attrs:
            if key.lower() == name and value:
                try:
                    return max(1, int(value.strip()))
                except ValueError:
                    return 1
        return 1

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._row = []
            self._in_header = False
        elif tag in {"td", "th"}:
            self._cell = []
            self._colspan = self._span(attrs, "colspan")
            self._rowspan = self._span(attrs, "rowspan")
            self._header_cell = tag == "th" or any(
                key.lower() == "scope" and (value or "").lower() == "col" for key, value in attrs
            )
            self._in_header = self._in_header or self._header_cell

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._cell is not None:
            text = normalize_text(" ".join(self._cell))
            self._row.append((text, self._colspan, self._rowspan))
            self._cell = None
        elif tag == "tr":
            self._flush()

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def _flush(self) -> None:
        """Lay this row out across columns, filling any position still spanned from above."""
        banner = len(self._row) == 1 and self._row[0][1] > 1 and not self._pending
        cells: list[str] = []
        opened: dict[int, tuple[str, int]] = {}
        column = 0
        cursor = iter(self._row)

        while True:
            carried = self._pending.get(column)
            if carried is not None:
                cells.append(carried[0])
                column += 1
                continue
            item = next(cursor, None)
            if item is None:
                break
            text, colspan, rowspan = item
            for _ in range(colspan):
                cells.append(text)
                if rowspan > 1:
                    opened[column] = (text, rowspan - 1)
                column += 1

        self._pending = {
            index: (text, rows - 1) for index, (text, rows) in self._pending.items() if rows - 1 > 0
        }
        self._pending.update(opened)
        self._row = []

        if not cells or banner:
            self._in_header = False
            return
        if self._in_header and not self.headers:
            self.headers = cells
        else:
            keys = self.headers or [f"col{i}" for i in range(len(cells))]
            self.rows.append(dict(zip(keys, cells, strict=False)))
        self._in_header = False


def extract_table_rows(html: str) -> list[dict[str, str]]:
    parser = _TableRows()
    parser.feed(html)
    parser.close()
    return parser.rows


class _MfdsFeedConnector:
    """Shared fetch shape for both MFDS surfaces."""

    key: ClassVar[str] = ""
    version: ClassVar[str] = "1.1.0"
    key_prefix: ClassVar[str] = "mfds:feed"
    #: The connector param that identifies the board upstream. See :meth:`identity`.
    identity_param: ClassVar[str] = "brdId"

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

    def identity(self, spec: SourceSpec) -> str:
        """The document identity for this feed.

        Keyed on what the *authority* calls the board, not on our source slug. Both gated cells
        subscribe to the same MFDS boards — 제개정고시등 announces 식품, 의약품, 의료기기 and
        화장품 alike — so a slug-derived key would create one Document per cell for one feed, which
        is the duplicate ADR-0002 decision 1 exists to prevent. Sharing the key means the feed is
        ingested once and *claimed* by every subscribing cell.
        """
        return str(spec.params.get(self.identity_param) or spec.slug)

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
                    canonical_key=f"{self.key_prefix}:{self.identity(spec)}",
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
    version: ClassVar[str] = "1.1.0"
    key_prefix: ClassVar[str] = "mfds:rss"
    identity_param: ClassVar[str] = "brdId"

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
    version: ClassVar[str] = "1.1.0"
    key_prefix: ClassVar[str] = "mfds:listing"
    identity_param: ClassVar[str] = "boardId"

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
