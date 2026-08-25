"""eCFR — the regulation text and the version spine for both FDA cells.

Two endpoints, and which does what is the whole of ADR-0018 decisions 4 and 6:

``versions/title-{n}.json?part=NNN``
    Per-section ``amendment_date`` · ``issue_date`` · ``removed`` · ``substantive``. This is the
    **detection** surface — the authority's own change history, structured, so a change is
    *reported* rather than inferred from a hash (ADR-0003 decision 12, promoted to primary here).
    It is also where a version's identity comes from: ``max(issue_date)`` over the Part's sections.

``full/{date}/title-{n}.xml?part=NNN``
    The body, at a stated date. Fetched **at the issue_date the versions endpoint gave**, never at
    "today" — so the archived bytes are addressable and a re-fetch of the same version reproduces
    them exactly. Point-in-time is real here and honoured, unlike the MFDS ``efYd`` trap
    (ADR-0016 decision 2).

**HTML is never fetched, from this host or from federalregister.gov** (ADR-0018 decision 11). The
publisher states that programmatic access belongs on the documented APIs, and an HTML request is
CAPTCHA-gated — a connector that fell back to a page would archive a bot check and call it a
regulation. There is no fallback path in this module, deliberately.

**No credential.** Every endpoint served anonymously across the reconnaissance, and no rate limit is
published; :class:`PoliteFetcher` backoff is reused unchanged. If the authority ever blocks us, the
answer is to slow down and use their *Site Help* channel — never to change ``User-Agent`` or spread
across addresses, which is the behaviour their policy exists to stop.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from typing import Any, ClassVar

from regops_shared.constants import DocType, DriftSignal

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
_PART = "part"

_HOST = "https://www.ecfr.gov"


def _versions_url(title: str, part: str) -> str:
    return f"{_HOST}/api/versioner/v1/versions/title-{title}.json?part={part}"


def _full_url(title: str, part: str, on: str) -> str:
    return f"{_HOST}/api/versioner/v1/full/{on}/title-{title}.xml?part={part}"


class ECFRConnector:
    """One CFR Part per source row. The Part is the Document (ADR-0018 decision 1)."""

    key: ClassVar[str] = "ecfr_part"
    version: ClassVar[str] = "1.0.0"
    key_prefix: ClassVar[str] = "fda:cfr"

    def __init__(self, fetcher: PoliteFetcher | None = None) -> None:
        self._fetcher = fetcher

    # -- identity ---------------------------------------------------------------------------

    def canonical_key(self, title: str, part: str) -> str:
        return f"{self.key_prefix}:{title}-{part}"

    # -- fetch ------------------------------------------------------------------------------

    def fetch(self, spec: SourceSpec) -> FetchResult:
        assert_ingestible(spec)
        title, part = self._target(spec)

        fetcher = self._fetcher or PoliteFetcher()
        try:
            versions = fetcher.get(_versions_url(title, part))
            if versions.status != 200:
                raise AuthorityError(
                    f"{spec.slug}: versions endpoint returned HTTP {versions.status}",
                    signal=DriftSignal.MISSING_ROOT,
                )
            rows = _content_versions(spec.slug, versions.body)
            issued_on = _latest_issue_date(spec.slug, rows)

            body = fetcher.get(
                _full_url(title, part, issued_on.isoformat()),
                etag=spec.http_etag,
                last_modified=spec.http_last_modified,
            )
        finally:
            if self._fetcher is None:
                fetcher.close()

        if body.not_modified:
            return FetchResult(http_status=body.status, not_modified=True)
        if body.status != 200:
            raise AuthorityError(
                f"{spec.slug}: body endpoint returned HTTP {body.status}",
                signal=DriftSignal.MISSING_ROOT,
            )
        if b"<DIV" not in body.body:
            # The 404 bodies are JSON — `{"error":"No matching content found."}` for a node that
            # does not exist, and a longer one naming the date ceiling for a future date. Both are
            # honest failures, and neither is a regulation.
            raise AuthorityError(
                f"{spec.slug}: response carries no CFR structural node",
                signal=DriftSignal.MISSING_ROOT,
            )

        artifact = FetchedArtifact(
            ref=ArtifactRef(
                canonical_key=self.canonical_key(title, part),
                title=spec.title,
                doc_type=DocType.REGULATION,
            ),
            raw=body.body,
            canonical=normalize_text(body.body.decode("utf-8", errors="replace")).encode(),
            content_type="application/xml",
            language="en",
            version_label=issued_on.isoformat(),
            #: The date the compilation issued this text — authority-stated, not our clock. The
            #: *legal* effective date comes from the Federal Register at version level
            #: (ADR-0018 decision 5); this is when the text became the operative compilation.
            published_at=datetime.combine(issued_on, datetime.min.time(), tzinfo=UTC),
            meta=_meta(rows, issued_on),
        )
        return FetchResult(
            http_status=body.status,
            artifacts=(artifact,),
            etag=body.etag,
            last_modified=body.last_modified,
        )

    # -- helpers ----------------------------------------------------------------------------

    @staticmethod
    def _target(spec: SourceSpec) -> tuple[str, str]:
        title = spec.params.get(_TITLE)
        part = spec.params.get(_PART)
        if not title or not part:
            raise AuthorityError(
                f"{spec.slug}: source params must carry {_TITLE!r} and {_PART!r}",
                signal=DriftSignal.MISSING_ROOT,
            )
        return str(title), str(part)


def _content_versions(slug: str, body: bytes) -> list[dict[str, Any]]:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as error:
        raise AuthorityError(
            f"{slug}: versions endpoint did not return JSON", signal=DriftSignal.MISSING_ROOT
        ) from error
    rows = payload.get("content_versions")
    if not isinstance(rows, list) or not rows:
        # A Part with no version rows is drift, not an empty Part: every live Part has a history.
        raise AuthorityError(
            f"{slug}: versions endpoint returned no content_versions",
            signal=DriftSignal.ZERO_RECORDS,
        )
    return [row for row in rows if isinstance(row, dict)]


def _latest_issue_date(slug: str, rows: list[dict[str, Any]]) -> date:
    """The Part's version identity: the newest ``issue_date`` across its sections.

    A Part's sections amend on different dates, so the Part has no single date of its own — the
    snapshot at the newest one *is* the current Part. Taking the max rather than a per-section date
    is what makes one ``DocumentVersion`` per distinct issue_date (ADR-0018 decision 4) rather than
    one per section, which would leave no single version of 21 CFR 820 to cite or diff against.
    """
    issued: list[date] = []
    for row in rows:
        raw = row.get("issue_date")
        if not raw:
            continue
        try:
            issued.append(date.fromisoformat(str(raw)))
        except ValueError:
            continue
    if not issued:
        raise AuthorityError(
            f"{slug}: no usable issue_date in content_versions", signal=DriftSignal.MISSING_ROOT
        )
    return max(issued)


def _meta(rows: list[dict[str, Any]], issued_on: date) -> dict[str, str]:
    """Envelope values the later stages need, and the counts that make a diff explicable.

    ``removed_sections`` is carried because the authority states removal and states no *move* —
    ADR-0002 decision 7's stated-renumber path does not exist for this authority, so the diff stage
    works from removal plus content similarity, and knowing what the authority itself called removed
    is the difference between "we lost it" and "they deleted it" (ADR-0018 decision 8).
    """
    at_issue = [r for r in rows if str(r.get("issue_date") or "") == issued_on.isoformat()]
    removed = [str(r.get("identifier") or "") for r in at_issue if r.get("removed")]
    substantive = [r for r in at_issue if r.get("substantive")]
    return {
        "issue_date": issued_on.isoformat(),
        "sections_at_issue": str(len(at_issue)),
        "sections_substantive": str(len(substantive)),
        "removed_sections": ",".join(sorted(x for x in removed if x)),
    }
