"""Federal Register — the effective date, and the only view of an amendment before it exists.

**This connector produces no regulation text, and that is correct.** A final rule announces a
change to the CFR; the CFR is what an RA cites (ADR-0018 decision 4). So a rule is not a Document
of its own — it is provenance, and the artefact here is a ``FEED``: a change signal carrying dates
and identifiers, which ``is_parseable`` refuses to segment into clauses because there is nothing in
it to cite. The MFDS RSS boards are modelled the same way, for the same reason.

Two things it exists to supply:

``effective_on``
    The **legally stated** effective date, a structured field (ADR-0018 decision 5). The eCFR's
    ``amendment_date`` says when the compilation absorbed a change; this says when the rule bit,
    and the two differ — the QMSR is ``effective_on`` 2026-02-02 and ``amendment_date`` 2026-02-04.
    It is **nullable**, and where it is null ADR-0013 applies: null with the ``dates`` prose
    retained, never a date we inferred.

Pending amendments
    The eCFR refuses future dates, so a rule published but not yet in force is invisible there —
    while the Federal Register carries five FDA rules today with a future effective date, one of
    them 2033-03-07 (ADR-0018 decision 7). This is the only surface that shows them, and seeing
    them is the whole reason the poll earns its request.

**One feed per CFR Part**, keyed ``fda:fr:{title}-{part}`` against the eCFR Document's
``fda:cfr:{title}-{part}``. Querying per Part rather than per cell makes the join decision 5 needs
structural instead of a search: the eCFR sources the same Part to ``89 FR 7523`` while this API
calls the rule ``89 FR 7496``, so citation strings cannot be joined on and the Part is what is left.

**A type filter is mandatory.** ``conditions[cfr]`` alone returns ``Proposed Rule`` alongside
``Rule``, and a proposed rule has no effective date and amends nothing.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from typing import Any, ClassVar
from urllib.parse import urlencode

from regops_shared.constants import DocType, DriftSignal

from ..canonicalize import canonical_records
from .base import (
    AnnouncementRecord,
    ArtifactRef,
    AuthorityError,
    FetchedArtifact,
    FetchResult,
    SourceSpec,
    assert_ingestible,
)
from .http import PoliteFetcher

_HOST = "https://www.federalregister.gov"

#: Requested explicitly rather than taking the default payload: the default carries abstracts and
#: agency blocks that change wording without any amendment, which would read as a change every poll.
_FIELDS: tuple[str, ...] = (
    "document_number",
    "citation",
    "title",
    "type",
    "publication_date",
    "effective_on",
    "cfr_references",
    "dates",
    "html_url",
)

#: One page. The API caps well above this and no in-scope Part came near it — 21 CFR 820 has 30
#: documents in its whole history. If a Part ever exceeds it the count is reported in ``meta``
#: rather than silently truncated.
_PER_PAGE = 100


def _query_url(title: str, part: str) -> str:
    params = [
        ("conditions[agencies][]", "food-and-drug-administration"),
        ("conditions[type][]", "RULE"),
        ("conditions[cfr][title]", title),
        ("conditions[cfr][part]", part),
        ("order", "newest"),
        ("per_page", str(_PER_PAGE)),
        *(("fields[]", field) for field in _FIELDS),
    ]
    return f"{_HOST}/api/v1/documents.json?{urlencode(params)}"


class FederalRegisterConnector:
    """Final rules affecting one CFR Part. Dates and identifiers, never regulation text."""

    key: ClassVar[str] = "federal_register"
    version: ClassVar[str] = "1.0.0"
    key_prefix: ClassVar[str] = "fda:fr"

    def __init__(self, fetcher: PoliteFetcher | None = None) -> None:
        self._fetcher = fetcher

    def canonical_key(self, title: str, part: str) -> str:
        return f"{self.key_prefix}:{title}-{part}"

    def fetch(self, spec: SourceSpec) -> FetchResult:
        assert_ingestible(spec)
        title, part = _target(spec)

        fetcher = self._fetcher or PoliteFetcher()
        try:
            response = fetcher.get(
                _query_url(title, part),
                etag=spec.http_etag,
                last_modified=spec.http_last_modified,
            )
        finally:
            if self._fetcher is None:
                fetcher.close()

        if response.not_modified:
            return FetchResult(http_status=response.status, not_modified=True)
        if response.status != 200:
            raise AuthorityError(
                f"{spec.slug}: HTTP {response.status}", signal=DriftSignal.MISSING_ROOT
            )

        payload = _payload(spec.slug, response.body)
        count = payload.get("count")
        results = payload.get("results")

        if count == 0 and results is None:
            # **Not drift.** When nothing matches, the API omits ``results`` entirely and answers
            # ``{"description": …, "count": 0}``. 21 CFR Part 710 does exactly this: it is an old
            # voluntary-registration Part with no FDA final rules at all, so an honest zero arrives
            # every poll. Raising here would file a structure-drift alert daily, for ever, about a
            # source that is working — the false-alert failure ADR-0003 decision 6 exists to avoid.
            # The observation still records that the source was checked.
            return FetchResult(http_status=response.status)

        if not isinstance(results, list):
            # No ``results`` *and* no zero count is a shape we do not recognise.
            raise AuthorityError(
                f"{spec.slug}: response carries neither a results array nor a zero count",
                signal=DriftSignal.MISSING_ROOT,
            )

        records = [_record(item) for item in results if isinstance(item, dict)]
        if not records:
            # ``results: []`` with a non-zero count is contradictory, and that *is* drift.
            raise AuthorityError(
                f"{spec.slug}: results array is empty while count is {count!r}",
                signal=DriftSignal.ZERO_RECORDS,
            )

        artifact = FetchedArtifact(
            ref=ArtifactRef(
                canonical_key=self.canonical_key(title, part),
                title=spec.title,
                doc_type=DocType.FEED,
            ),
            raw=response.body,
            canonical=canonical_records(records),
            content_type="application/json",
            language="en",
            published_at=_newest_publication(records),
            meta=_meta(records, reported_total=payload.get("count")),
        )
        return FetchResult(
            http_status=response.status,
            artifacts=(artifact,),
            announcements=tuple(_announcement(item) for item in results if isinstance(item, dict)),
            etag=response.etag,
            last_modified=response.last_modified,
        )


def _announcement(item: dict[str, Any]) -> AnnouncementRecord:
    """One rule as a durable row (ADR-0019), beside the feed artefact that archives the response.

    ``affects`` is emitted as **canonical keys** rather than part numbers because the key convention
    is the connector's to know — ``fda:cfr:21-820`` pairs with the eCFR Document of the same Part,
    which is the structural join ADR-0018 decision 5 needs.
    """
    refs = item.get("cfr_references")
    affects: tuple[str, ...] = ()
    if isinstance(refs, list):
        affects = tuple(
            sorted(
                f"fda:cfr:{ref.get('title')}-{ref.get('part')}"
                for ref in refs
                if isinstance(ref, dict) and ref.get("title") and ref.get("part")
            )
        )
    return AnnouncementRecord(
        ref=str(item.get("document_number") or ""),
        authority="fda",
        affects=affects,
        citation=str(item.get("citation") or "") or None,
        title=str(item.get("title") or "") or None,
        published_on=str(item.get("publication_date") or "") or None,
        effective_on=str(item.get("effective_on") or "") or None,
        effective_date_phrase=str(item.get("dates") or "") or None,
        official_url=str(item.get("html_url") or "") or None,
    )


def _target(spec: SourceSpec) -> tuple[str, str]:
    title = spec.params.get("title")
    part = spec.params.get("part")
    if not title or not part:
        raise AuthorityError(
            f"{spec.slug}: source params must carry 'title' and 'part'",
            signal=DriftSignal.MISSING_ROOT,
        )
    return str(title), str(part)


def _payload(slug: str, body: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as error:
        raise AuthorityError(
            f"{slug}: response was not JSON", signal=DriftSignal.MISSING_ROOT
        ) from error
    if not isinstance(payload, dict):
        raise AuthorityError(f"{slug}: response was not an object", signal=DriftSignal.MISSING_ROOT)
    return payload


def _record(item: dict[str, Any]) -> dict[str, str]:
    """One rule, flattened to strings so the canonical form is stable across polls.

    ``cfr_references`` arrives as a list of objects and is flattened to ``21-4,21-820``, **sorted**:
    the API's ordering is not guaranteed, and an unstable order would hash differently every poll
    and report an amendment that did not happen.
    """
    refs = item.get("cfr_references")
    flattened = ""
    if isinstance(refs, list):
        pairs = sorted(
            f"{ref.get('title')}-{ref.get('part')}" for ref in refs if isinstance(ref, dict)
        )
        flattened = ",".join(pairs)
    return {
        "document_number": str(item.get("document_number") or ""),
        "citation": str(item.get("citation") or ""),
        "type": str(item.get("type") or ""),
        "publication_date": str(item.get("publication_date") or ""),
        # Nullable, and stored as empty rather than as a guess — ADR-0013.
        "effective_on": str(item.get("effective_on") or ""),
        "cfr_references": flattened,
        # The prose that becomes ``effective_date_phrase`` where the date is missing or conditional.
        "dates": str(item.get("dates") or ""),
        "html_url": str(item.get("html_url") or ""),
    }


def _as_date(raw: str) -> date | None:
    try:
        return date.fromisoformat(raw) if raw else None
    except ValueError:
        return None


def _newest_publication(records: list[dict[str, str]]) -> datetime | None:
    """The feed's own date. Never our fetch clock, which would make the latency gate
    self-fulfilling."""
    published = [d for d in (_as_date(r["publication_date"]) for r in records) if d]
    if not published:
        return None
    return datetime.combine(max(published), datetime.min.time(), tzinfo=UTC)


def _meta(records: list[dict[str, str]], *, reported_total: object) -> dict[str, str]:
    """What the version stage and ADR-0018 decision 7 need, plus an honest truncation count."""
    effective = {r["document_number"]: _as_date(r["effective_on"]) for r in records}
    stated = {k: v for k, v in effective.items() if v is not None}
    pending = sorted(v for v in stated.values() if v > date.today())

    meta = {
        "rules_returned": str(len(records)),
        "rules_without_effective_date": str(len(records) - len(stated)),
        "pending_count": str(len(pending)),
    }
    if pending:
        # The size of the blind spot decision 7 names: announced, and not yet readable anywhere.
        meta["earliest_pending"] = pending[0].isoformat()
        meta["latest_pending"] = pending[-1].isoformat()
    if isinstance(reported_total, int) and reported_total > len(records):
        # Never a silent cap. If this appears, the query needs paging before the feed is trusted.
        meta["truncated_of_total"] = str(reported_total)
    return meta
