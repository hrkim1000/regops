"""The network half of the measurement. Needs the service container; :mod:`fda_lag.probe` does not.

Split out so the lag arithmetic stays importable on the host, where the test gate runs. Importing
this module inserts ``/app`` on the path, so it only resolves inside a service container.

``PoliteFetcher`` is reused rather than reimplemented — it identifies itself, throttles per host,
backs off with jitter and honours ``Retry-After``, which is the same politeness contract
[phase2.0a](../../docs/plan/phase2.0a_fda.md) requires of the FDA connectors. Two side benefits:
the two-week run doubles as the rate-limit observation the spike left `[ ]`, and it returns a
``HttpResponse`` for any non-retryable status instead of raising, so a 404 is data.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

sys.path.insert(0, "/app")

from app.connectors.http import PoliteFetcher, redact_url
from fda_lag.probe import (
    CFR_TITLE,
    DEFAULT_LOOKBACK_DAYS,
    DEFAULT_PAIR_TOLERANCE_DAYS,
    ECFR_HOST,
    FR_FIELDS,
    FR_HOST,
    FR_PAGE_SIZE,
    IN_SCOPE_PARTS,
    FinalRule,
    Observation,
    ProbeError,
    SectionVersion,
    TitleState,
    blind_spot_days,
    freshness_lag_days,
    pair_candidates,
    unabsorbed_rules,
)

__all__ = [
    "PoliteFetcher",
    "fetch_final_rules",
    "fetch_section_versions",
    "fetch_title_state",
    "observe",
]


def _get_json(fetcher: PoliteFetcher, url: str) -> dict[str, Any]:
    safe = redact_url(url)
    response = fetcher.get(url)
    if response.status != 200:
        raise ProbeError(f"{safe}: HTTP {response.status} — {response.body[:200]!r}")
    try:
        payload = json.loads(response.body)
    except json.JSONDecodeError as exc:
        raise ProbeError(f"{safe}: body is not JSON ({exc})") from exc
    if not isinstance(payload, dict):
        raise ProbeError(f"{safe}: expected a JSON object, got {type(payload).__name__}")
    return payload


def fetch_title_state(fetcher: PoliteFetcher, *, title: int = CFR_TITLE) -> TitleState:
    payload = _get_json(fetcher, f"{ECFR_HOST}/api/versioner/v1/titles.json")
    for row in payload.get("titles", []):
        if isinstance(row, dict) and row.get("number") == title:
            return TitleState(
                up_to_date_as_of=row.get("up_to_date_as_of"),
                latest_amended_on=row.get("latest_amended_on"),
                latest_issue_date=row.get("latest_issue_date"),
                import_in_progress=bool(payload.get("meta", {}).get("import_in_progress")),
            )
    raise ProbeError(f"titles.json returned no entry for title {title}")


def fetch_section_versions(
    fetcher: PoliteFetcher, *, since: date, title: int = CFR_TITLE
) -> tuple[tuple[SectionVersion, ...], bool]:
    """Section-versions issued on or after ``since``. Returns ``(rows, truncated)``."""
    query = urlencode({"issue_date[gte]": since.isoformat()})
    payload = _get_json(
        fetcher, f"{ECFR_HOST}/api/versioner/v1/versions/title-{title}.json?{query}"
    )
    raw = payload.get("content_versions") or []
    rows = tuple(
        SectionVersion(
            identifier=str(row.get("identifier") or ""),
            part=str(row["part"]) if row.get("part") is not None else None,
            subpart=str(row["subpart"]) if row.get("subpart") is not None else None,
            issue_date=row.get("issue_date"),
            amendment_date=row.get("amendment_date"),
            removed=bool(row.get("removed")),
            substantive=bool(row.get("substantive")),
        )
        for row in raw
        if isinstance(row, dict)
    )
    stated = payload.get("meta", {}).get("result_count")
    truncated = stated is not None and int(stated) > len(rows)
    return rows, truncated


def fetch_final_rules(
    fetcher: PoliteFetcher, *, since: date, title: int = CFR_TITLE
) -> tuple[tuple[FinalRule, ...], bool]:
    """FDA final rules published on or after ``since``. Returns ``(rules, truncated)``.

    ``conditions[type][]=RULE`` is mandatory: without it the same query returns Proposed Rules,
    which announce nothing that will land in the compilation.
    """
    params: list[tuple[str, str]] = [
        ("per_page", str(FR_PAGE_SIZE)),
        ("order", "newest"),
        ("conditions[agencies][]", "food-and-drug-administration"),
        ("conditions[type][]", "RULE"),
        ("conditions[publication_date][gte]", since.isoformat()),
        *(("fields[]", name) for name in FR_FIELDS),
    ]
    payload = _get_json(fetcher, f"{FR_HOST}/api/v1/documents.json?{urlencode(params)}")
    results = payload.get("results") or []
    rules = tuple(
        FinalRule(
            document_number=str(row.get("document_number") or ""),
            citation=row.get("citation"),
            doc_type=row.get("type"),
            publication_date=row.get("publication_date"),
            effective_on=row.get("effective_on"),
            parts=tuple(
                str(ref["part"])
                for ref in (row.get("cfr_references") or [])
                if isinstance(ref, dict)
                and ref.get("part") is not None
                and ref.get("title") == title
            ),
            title=row.get("title"),
        )
        for row in results
        if isinstance(row, dict)
    )
    count = payload.get("count")
    truncated = count is not None and int(count) > len(rules)
    return rules, truncated


def observe(
    fetcher: PoliteFetcher,
    *,
    now: datetime | None = None,
    observed_on: date | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    tolerance_days: int = DEFAULT_PAIR_TOLERANCE_DAYS,
    title: int = CFR_TITLE,
) -> Observation:
    """One observation. ``observed_on`` overrides the calendar day the run is filed under.

    **The two timestamps mean different things and are allowed to disagree by a day.**
    ``observed_at`` is the instant the fetch happened, in UTC, and is provenance. ``observed_on`` is
    the day the observation is *filed under*, and the series counts distinct values of it — so it
    has to mean the operator's day, not the container's.

    The container runs UTC; the operator does not have to. At UTC+9 every run before 09:00 local
    falls on the previous UTC date, which would file a fresh observation under a day already in the
    log — and the wrapper's "already recorded" guard would then decline to append it, silently
    costing a day out of ten. So the wrapper passes its own local date and this honours it.
    """
    moment = now or datetime.now(UTC)
    observed_on = observed_on or moment.date()
    since = observed_on - timedelta(days=lookback_days)

    state = fetch_title_state(fetcher, title=title)
    versions, versions_truncated = fetch_section_versions(fetcher, since=since, title=title)
    rules, rules_truncated = fetch_final_rules(fetcher, since=since, title=title)
    pairings = pair_candidates(versions, rules, tolerance_days=tolerance_days)

    notes: list[str] = []
    if state.import_in_progress:
        notes.append(
            "eCFR reported import_in_progress — this title may have been served mid-import, "
            "so treat the section-version rows as provisional"
        )
    if versions_truncated:
        notes.append("eCFR versions response was truncated against its own result_count")
    if rules_truncated:
        notes.append(
            f"Federal Register count exceeded per_page={FR_PAGE_SIZE}; "
            "older rules in the window are missing"
        )

    stale = unabsorbed_rules(
        rules, up_to_date_as_of=state.up_to_date_as_of, observed_on=observed_on
    )
    if stale:
        notes.append(
            f"{len(stale)} rule(s) are in force but not yet in the compilation — the eCFR claims "
            f"currency as of {state.up_to_date_as_of}: "
            + ", ".join(f"{rule.document_number} (effective {rule.effective_on})" for rule in stale)
        )

    return Observation(
        observed_at=moment.isoformat(),
        observed_on=observed_on.isoformat(),
        lookback_from=since.isoformat(),
        title=title,
        freshness_lag_days=freshness_lag_days(observed_on, state.up_to_date_as_of),
        blind_spot_days=blind_spot_days(
            rules, up_to_date_as_of=state.up_to_date_as_of, observed_on=observed_on
        ),
        unabsorbed_rules=[rule.document_number for rule in stale],
        title_state=asdict(state),
        in_scope_parts=sorted(IN_SCOPE_PARTS),
        section_versions=[asdict(version) for version in versions],
        final_rules=[asdict(rule) for rule in rules],
        pairings=[asdict(pairing) for pairing in pairings],
        truncated={"ecfr_versions": versions_truncated, "federal_register": rules_truncated},
        notes=notes,
    )
