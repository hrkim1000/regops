"""Tier D freshness, tracked through the recognition list rather than through the standard.

The recognition/harmonized **list** is an ingestible Tier B page; the standard it names is never
fetched (ADR-0003 decision 7). So this connector is the one place Tier D data enters RegOps, and it
is shaped so that it *cannot* carry body text:

- It returns :class:`StandardRecord` values and ``artifacts=()``. ``StandardRecord`` has no bytes
  field, so there is nothing to archive and no WORM write on this path.
- The rows it produces land in ``standard_references``, which has no ``text`` column and no varchar
  over 512 characters.

Together with ``sources.ingestible = false`` on the Tier D rows themselves and the
:func:`assert_ingestible` check at every other connector's entry point, that is four independent
places the rule holds. The CI string scan is the backstop, not the mechanism.

Column names differ per authority, so the header→field mapping is configuration
(``sources.params["columns"]``) rather than code — an FDA Recognized Consensus Standards table and
an MFDS 인정 목록 are the same shape with different labels.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import ClassVar

from regops_shared.constants import DriftSignal, StandardStatus

from ..canonicalize import normalize_text
from .base import (
    AuthorityError,
    FetchResult,
    SourceSpec,
    StandardRecord,
)
from .http import PoliteFetcher
from .mfds import extract_table_rows

#: Field name → the header labels that map onto it, when the source does not configure its own.
DEFAULT_COLUMNS: Mapping[str, tuple[str, ...]] = {
    "number": ("표준번호", "standard", "standard number", "번호"),
    "edition": ("판", "edition", "version", "발행연도"),
    "issuing_body": ("제정기관", "issuing body", "organization", "기관"),
    "recognition_number": ("인정번호", "recognition number", "recognition no", "고시번호"),
    "title": ("표준명", "title", "명칭"),
    "effective_date": ("인정일", "효력발생일", "effective date", "date of entry"),
    "withdrawal_date": ("철회일", "withdrawal date", "date of withdrawal"),
    "official_url": ("링크", "url", "link"),
}

_STATUS_BY_KEYWORD: Mapping[str, StandardStatus] = {
    "인정": StandardStatus.RECOGNIZED,
    "recognized": StandardStatus.RECOGNIZED,
    "harmonised": StandardStatus.HARMONIZED,
    "harmonized": StandardStatus.HARMONIZED,
    "철회": StandardStatus.WITHDRAWN,
    "withdrawn": StandardStatus.WITHDRAWN,
    "대체": StandardStatus.SUPERSEDED,
    "superseded": StandardStatus.SUPERSEDED,
}


def _match_column(row: Mapping[str, str], labels: tuple[str, ...]) -> str | None:
    normalized = {normalize_text(k).lower(): v for k, v in row.items()}
    for label in labels:
        value = normalized.get(label.lower())
        if value:
            return normalize_text(value)
    return None


def _status_of(row: Mapping[str, str]) -> str:
    blob = " ".join(row.values()).lower()
    for keyword, status in _STATUS_BY_KEYWORD.items():
        if keyword in blob:
            return status.value
    return StandardStatus.UNKNOWN.value


def row_to_record(
    row: Mapping[str, str], columns: Mapping[str, tuple[str, ...]]
) -> StandardRecord | None:
    """One list row → one recognition record, or None if the row names no standard."""
    number = _match_column(row, columns.get("number", ()))
    if not number:
        return None
    return StandardRecord(
        number=number,
        edition=_match_column(row, columns.get("edition", ())),
        issuing_body=_match_column(row, columns.get("issuing_body", ())),
        recognition_number=_match_column(row, columns.get("recognition_number", ())),
        title=_match_column(row, columns.get("title", ())),
        effective_date=_match_column(row, columns.get("effective_date", ())),
        withdrawal_date=_match_column(row, columns.get("withdrawal_date", ())),
        status=_status_of(row),
        official_url=_match_column(row, columns.get("official_url", ())),
    )


class RecognitionListConnector:
    """Fetches the list. Never the standard."""

    key: ClassVar[str] = "recognition_list"
    version: ClassVar[str] = "1.0.0"

    def __init__(self, fetcher: PoliteFetcher | None = None) -> None:
        self._fetcher = fetcher

    def fetch(self, spec: SourceSpec) -> FetchResult:
        # Deliberately no `assert_ingestible` bypass: the *list* is Tier B and ingestible. The
        # Tier D rows this produces are seeded with `ingestible = false` and have no fetch path.
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

        return FetchResult(
            http_status=response.status,
            standards=self.parse(response.body, spec=spec),
            etag=response.etag,
            last_modified=response.last_modified,
        )

    def parse(self, body: bytes, *, spec: SourceSpec) -> tuple[StandardRecord, ...]:
        configured = spec.params.get("columns")
        columns: Mapping[str, tuple[str, ...]] = (
            {k: tuple(v) for k, v in configured.items()}  # type: ignore[union-attr]
            if isinstance(configured, Mapping)
            else DEFAULT_COLUMNS
        )

        rows = extract_table_rows(body.decode("utf-8", errors="replace"))
        records = tuple(r for row in rows if (r := row_to_record(row, columns)) is not None)
        if not records:
            raise AuthorityError(
                f"{spec.slug}: recognition list yielded no standards — the table layout changed",
                signal=DriftSignal.ZERO_RECORDS,
            )
        return records


__all__ = ["DEFAULT_COLUMNS", "RecognitionListConnector", "row_to_record"]
