"""govinfo — the FD&C Act, which is the statute both FDA cells sit under.

21 U.S.C. chapter 9 *is* the Federal Food, Drug, and Cosmetic Act: govinfo titles the chapter
granule exactly that. One Document, claimed by ``fda_samd`` and ``fda_cosmetic`` alike through
``document_cells`` — the first source in the corpus where two cells share an instrument rather than
each having their own, which is the M:N case phase 2.0a exists to exercise.

**One fetch, the whole Act.** The chapter granule carries all 309 section heads in a single 5.4 MB
response, so the Document arrives as one artifact and one archived object. The 163-granule figure
from the first reconnaissance was an artifact of that probe reading only the first page of 901
granules, not a property of the chapter.

**The version is the annual edition, and that is accepted rather than worked around**
(ADR-0018 decision 12). ``version_label`` is the package id — ``USCODE-2024-title21`` — so the
version key stays the authority's own, exactly as ``ecfr_part`` uses the eCFR's ``issue_date``.
The consequence is stated where it belongs and must not be averaged away: **the statute does not
meet the ≤24h detection gate**, because its publisher does not republish it faster than yearly.
``PLAW``, which does carry enactments as they happen, is deliberately not built here.

**The key travels in a header, never in the URL.** api.govinfo.gov accepts ``api_key`` as a query
parameter, and using it that way would write a live credential into ``sources.url_template`` and
into every logged URL. :meth:`PoliteFetcher.get` takes ``extra_headers`` for this.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from typing import Any, ClassVar

from regops_shared.constants import DocType, DriftSignal
from regops_shared.settings import get_settings

from ..canonicalize import normalize_text
from .base import (
    ArtifactRef,
    AuthorityError,
    FetchedArtifact,
    FetchResult,
    SourceSpec,
    assert_ingestible,
)
from .http import PoliteFetcher

#: ``sources.params`` keys this connector reads.
_TITLE = "title"
_CHAPTER = "chapter"

_HOST = "https://api.govinfo.gov"

#: How many editions back to look for the newest one that exists.
#:
#: The edition year is the only thing here taken from our own clock, and it is a *candidate* only —
#: a year is accepted because the package summary answers 200, never because we believe in it. Four
#: steps covers the ordinary case (the 2024 edition was issued 2024-12-31 and is still current well
#: into the following year) and a publication slip, without turning a stale deployment into a silent
#: sweep back through the archive.
_MAX_LOOKBACK_YEARS = 4


def _package_id(title: str, year: int) -> str:
    return f"USCODE-{year}-title{title}"


def _summary_url(package: str) -> str:
    return f"{_HOST}/packages/{package}/summary"


def _granule_url(package: str, granule: str) -> str:
    return f"{_HOST}/packages/{package}/granules/{granule}/htm"


class GovInfoUSCodeConnector:
    """One USC chapter per source row. The chapter is the Document (ADR-0018 decision 12)."""

    key: ClassVar[str] = "govinfo_uscode"
    version: ClassVar[str] = "1.0.0"
    key_prefix: ClassVar[str] = "fda:usc"

    def __init__(self, fetcher: PoliteFetcher | None = None) -> None:
        self._fetcher = fetcher

    # -- identity ---------------------------------------------------------------------------

    def canonical_key(self, title: str, chapter: str) -> str:
        return f"{self.key_prefix}:{title}-{chapter}"

    # -- fetch ------------------------------------------------------------------------------

    def fetch(self, spec: SourceSpec) -> FetchResult:
        assert_ingestible(spec)
        title, chapter = self._target(spec)
        headers = _auth_headers(spec.slug)

        fetcher = self._fetcher or PoliteFetcher()
        try:
            package, issued_on = self._latest_edition(fetcher, spec.slug, title, headers)
            granule = f"{package}-chap{chapter}"
            body = fetcher.get(
                _granule_url(package, granule),
                etag=spec.http_etag,
                last_modified=spec.http_last_modified,
                extra_headers=headers,
            )
        finally:
            if self._fetcher is None:
                fetcher.close()

        if body.not_modified:
            return FetchResult(http_status=body.status, not_modified=True)
        if body.status != 200:
            raise AuthorityError(
                f"{spec.slug}: granule {granule} returned HTTP {body.status}",
                signal=DriftSignal.MISSING_ROOT,
            )
        if b'class="section-head"' not in body.body:
            # The chapter carries 309 of these. A body without one is a redesign, an error page or
            # a chapter that has been restructured out from under us — none of which is a statute,
            # and all of which must fail before a version is written (ADR-0003 decision 6).
            raise AuthorityError(
                f"{spec.slug}: granule {granule} carries no section-head block",
                signal=DriftSignal.MISSING_ROOT,
            )

        artifact = FetchedArtifact(
            ref=ArtifactRef(
                canonical_key=self.canonical_key(title, chapter),
                title=spec.title,
                doc_type=DocType.CODIFIED_STATUTE,
            ),
            raw=body.body,
            canonical=normalize_text(body.body.decode("utf-8", errors="replace")).encode(),
            content_type="text/html",
            language="en",
            #: The authority's own name for the edition, so a re-fetch of the same version is
            #: addressable and reproduces the same bytes.
            version_label=package,
            published_at=datetime.combine(issued_on, datetime.min.time(), tzinfo=UTC),
            meta={
                "package_id": package,
                "granule_id": granule,
                "date_issued": issued_on.isoformat(),
            },
        )
        return FetchResult(
            http_status=body.status,
            artifacts=(artifact,),
            etag=body.etag,
            last_modified=body.last_modified,
        )

    # -- helpers ----------------------------------------------------------------------------

    def _latest_edition(
        self, fetcher: PoliteFetcher, slug: str, title: str, headers: dict[str, str]
    ) -> tuple[str, date]:
        """The newest published edition of this title, and the date the authority issued it.

        Walks candidate years downward and stops at the first that exists. The year is ours; the
        acceptance is the publisher's, and ``dateIssued`` comes back from them rather than being
        derived from the year we guessed.
        """
        current = datetime.now(tz=UTC).year
        for year in range(current, current - _MAX_LOOKBACK_YEARS, -1):
            package = _package_id(title, year)
            response = fetcher.get(_summary_url(package), extra_headers=headers)
            if response.status == 404:
                continue
            if response.status != 200:
                raise AuthorityError(
                    f"{slug}: package summary for {package} returned HTTP {response.status}",
                    signal=DriftSignal.MISSING_ROOT,
                )
            return package, _date_issued(slug, package, response.body)

        raise AuthorityError(
            f"{slug}: no USCODE edition of title {title} found in the last "
            f"{_MAX_LOOKBACK_YEARS} years",
            signal=DriftSignal.ZERO_RECORDS,
        )

    @staticmethod
    def _target(spec: SourceSpec) -> tuple[str, str]:
        title = spec.params.get(_TITLE)
        chapter = spec.params.get(_CHAPTER)
        if not title or not chapter:
            raise AuthorityError(
                f"{spec.slug}: source params must carry {_TITLE!r} and {_CHAPTER!r}",
                signal=DriftSignal.MISSING_ROOT,
            )
        return str(title), str(chapter)


def _auth_headers(slug: str) -> dict[str, str]:
    key = get_settings().govinfo_api_key
    if not key:
        # Anonymous access is 401, not a reduced quota, so there is nothing to degrade to.
        raise AuthorityError(
            f"{slug}: GOVINFO_API_KEY is not configured", signal=DriftSignal.MISSING_ROOT
        )
    return {"X-Api-Key": key}


def _date_issued(slug: str, package: str, body: bytes) -> date:
    payload: Any
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as error:
        raise AuthorityError(
            f"{slug}: package summary for {package} did not return JSON",
            signal=DriftSignal.MISSING_ROOT,
        ) from error
    raw = payload.get("dateIssued") if isinstance(payload, dict) else None
    if not isinstance(raw, str):
        raise AuthorityError(
            f"{slug}: package summary for {package} carries no dateIssued",
            signal=DriftSignal.MISSING_ROOT,
        )
    try:
        return date.fromisoformat(raw[:10])
    except ValueError as error:
        raise AuthorityError(
            f"{slug}: package summary for {package} has an unreadable dateIssued {raw!r}",
            signal=DriftSignal.MISSING_ROOT,
        ) from error


__all__ = ["GovInfoUSCodeConnector"]
