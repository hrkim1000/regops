"""Lag arithmetic and the observation record. **Pure — no network, no service imports.**

Kept free of ``app.*`` on purpose: the fetch layer lives in :mod:`fda_lag.fetch` and needs the
service container, while everything that decides what a number *means* is here and therefore
testable by the host-side gate. The reasoning this module encodes is the part worth a test; an HTTP
GET is not.

**Three lags, never conflated.** Collapsing them is the mistake this module exists to prevent,
because only the first one bounds the detection gate:

``freshness_lag_days``
    Observation date - the title's ``up_to_date_as_of``. How stale the compilation is *right now*.
    This is the one the ≤24h detection-latency gate rests on, and it is sampled on every run
    whether or not anything was amended.

``absorption_lag_days``
    An eCFR section's ``issue_date`` - the Federal Register rule's ``effective_on``. How long after
    a rule bites the compiled text shows it. Measured on the QMSR at +2 days
    (effective 2026-02-02, absorbed 2026-02-04), which is why it is tracked separately: a two-day
    absorption with a one-day freshness lag are different problems with different fixes.

``announcement_lead_days``
    A rule's ``effective_on`` - its ``publication_date``. The pending window — 0 to 163 days in the
    spike sample, and one rule on the books leads by seven years. Not a lag in our pipeline at all;
    it is how much warning the authority gives, and it is recorded because ADR-0018 decision 7 says
    a pending amendment produces no version, so this is the only number describing that gap.

**Why the window is the whole title and not the parts in scope.** Over the seven weeks the spike
sampled, exactly **2** section amendments touched a Part the FDA cells claim. A fortnight restricted
to those Parts would very likely record zero, and an empty file is not a measurement. So every
title-21 row in the window is captured and the in-scope ones are *tagged*. A stale
:data:`IN_SCOPE_PARTS` therefore degrades a label, never the data — which is what keeps this from
being the second source catalog CLAUDE.md forbids. The list used is written into every observation,
so drift against ``docs/import-source-map.md`` shows up in the output rather than hiding in here.

**Why a lookback window rather than "since the last run".** A missed day self-heals: the next run
re-covers it. Chaining on last-seen state would turn one skipped morning into a permanent hole, and
this runs for two weeks on somebody's attention.

**What this measurement cannot do.** ``up_to_date_as_of`` is a *date*. No arrangement of these calls
resolves the freshness lag below day granularity, so a "≤24h" claim cannot be *proved* here. What a
fortnight does settle is the question the ADR actually asks — whether the lag sits at 0–1 days, and
the gate is reachable through the eCFR, or at 3+ days, and it is not.
"""

from __future__ import annotations

import json
import statistics
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Final

#: The only CFR title the FDA cells draw on. Both cells; every Part in the source map lives here.
CFR_TITLE: Final[int] = 21

ECFR_HOST: Final[str] = "https://www.ecfr.gov"
FR_HOST: Final[str] = "https://www.federalregister.gov"

#: Days of history each run re-reads. Generous on purpose — see the lookback note above. Cheap:
#: 30 days of title-21 section versions was ~15 KB in the spike.
DEFAULT_LOOKBACK_DAYS: Final[int] = 30

#: How far apart an eCFR ``issue_date`` and a rule's ``effective_on`` may sit and still be treated
#: as candidates for the same amendment. The spike measured +2 on the QMSR; this allows slack in
#: both directions without pairing across unrelated amendments of the same Part.
DEFAULT_PAIR_TOLERANCE_DAYS: Final[int] = 10

#: Page size for the Federal Register list. Responses state ``count``, so a window that overflows
#: this is reported as truncated rather than silently clipped.
FR_PAGE_SIZE: Final[int] = 200

#: The Parts the two FDA cells claim, per ``docs/import-source-map.md`` § Region 2 as of 2026-08-24.
#: **A label, not a filter** — every title-21 row in the window is recorded regardless. The
#: authoritative list is the source map; this copy exists because ``docs/`` is not mounted into the
#: service container, and it is echoed into each observation so divergence is visible in the data.
IN_SCOPE_PARTS: Final[frozenset[str]] = frozenset(
    {"7", "11", "700", "701", "710", "740", "803", "806", "807", "820", "822", "860", "892"}
)

FR_FIELDS: Final[tuple[str, ...]] = (
    "document_number",
    "citation",
    "type",
    "publication_date",
    "effective_on",
    "cfr_references",
    "title",
)


class ProbeError(RuntimeError):
    """A probe could not be completed. Carries the safe URL and what came back."""


# --- records ------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TitleState:
    """The title's own freshness statement — the numerator of the lag that matters."""

    up_to_date_as_of: str | None
    latest_amended_on: str | None
    latest_issue_date: str | None
    import_in_progress: bool


@dataclass(frozen=True, slots=True)
class SectionVersion:
    """One row of the eCFR ``versions`` endpoint — a section-version, as the authority states it."""

    identifier: str
    part: str | None
    subpart: str | None
    issue_date: str | None
    amendment_date: str | None
    removed: bool
    substantive: bool

    @property
    def in_scope(self) -> bool:
        return self.part in IN_SCOPE_PARTS


@dataclass(frozen=True, slots=True)
class FinalRule:
    """A Federal Register document. ``effective_on`` is nullable — one in five, in the spike."""

    document_number: str
    citation: str | None
    doc_type: str | None
    publication_date: str | None
    effective_on: str | None
    parts: tuple[str, ...]
    title: str | None


@dataclass(frozen=True, slots=True)
class Pairing:
    """A section-version beside the rules that could account for it.

    Deliberately **not** a join. The spike established that the citation strings do not match —
    the eCFR sources part 820 to ``89 FR 7523`` while the Federal Register calls the same rule
    ``89 FR 7496``, because 7523 is the page inside it where the Part begins. So attribution is by
    Part plus date proximity, and ``candidates``/``ambiguous`` keep the uncertainty visible instead
    of resolving it silently.
    """

    section: str
    part: str | None
    issue_date: str | None
    in_scope: bool
    removed: bool
    substantive: bool
    candidates: tuple[str, ...]
    absorption_lag_days: int | None
    basis: str | None
    ambiguous: bool


@dataclass(slots=True)
class Observation:
    """One run. Serialized as a single JSON line so the log is append-only and diff-friendly."""

    observed_at: str
    observed_on: str
    lookback_from: str
    title: int
    freshness_lag_days: int | None
    #: The corroborated lag — see :func:`blind_spot_days`. This is the verdict input;
    #: ``freshness_lag_days`` is context that cannot tell "quiet" from "behind".
    blind_spot_days: int
    unabsorbed_rules: list[str]
    title_state: dict[str, Any]
    in_scope_parts: list[str]
    section_versions: list[dict[str, Any]]
    final_rules: list[dict[str, Any]]
    pairings: list[dict[str, Any]]
    truncated: dict[str, bool]
    notes: list[str] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)


# --- lag arithmetic -----------------------------------------------------------------------


def as_date(value: str | None) -> date | None:
    """Parse an authority-supplied date. A malformed value is ``None``, never an exception:
    the point of the run is to record what came back, not to die on one odd field."""
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def freshness_lag_days(observed_on: date, up_to_date_as_of: str | None) -> int | None:
    """Whole days between the observation and the title's own freshness statement.

    ``None`` when the endpoint stated no date — recorded as absent rather than as zero, because a
    missing freshness claim and a fresh title are opposite findings.
    """
    stated = as_date(up_to_date_as_of)
    if stated is None:
        return None
    return (observed_on - stated).days


def announcement_lead_days(rule: FinalRule) -> int | None:
    """``effective_on - publication_date``. ``None`` when the rule states no effective date."""
    published, effective = as_date(rule.publication_date), as_date(rule.effective_on)
    if published is None or effective is None:
        return None
    return (effective - published).days


def unabsorbed_rules(
    rules: Iterable[FinalRule], *, up_to_date_as_of: str | None, observed_on: date
) -> tuple[FinalRule, ...]:
    """Rules **in force** that the compilation demonstrably has not absorbed yet.

    This, not :func:`freshness_lag_days`, is what bounds detection latency — and the first live run
    is why the distinction exists. It measured ``freshness_lag_days = 4`` (observed 2026-08-24,
    ``up_to_date_as_of`` 2026-08-20), which read naively says the eCFR is four days behind and
    cannot carry a ≤24h gate. But 2026-08-21 to 08-23 was a weekend: a compilation that does not
    advance because **nothing was amended**, and one that does not advance because it is *behind*,
    produce the identical number — and they are opposite findings.

    A rule counts here only when the authority contradicts itself — the rule took effect on or
    before the observation, yet the title claims currency as of a date before that. There is no
    interpretation of those two statements under which the text is present.
    """
    boundary = as_date(up_to_date_as_of)
    if boundary is None:
        return ()
    return tuple(
        rule
        for rule in rules
        if (effective := as_date(rule.effective_on)) is not None
        and boundary < effective <= observed_on
    )


def blind_spot_days(
    rules: Iterable[FinalRule], *, up_to_date_as_of: str | None, observed_on: date
) -> int:
    """Days since the oldest in-force-but-unabsorbed rule took effect. ``0`` when there are none.

    Zero is the good answer and it is not the same as "no data": it means every rule in force is in
    the compilation, which is exactly what ADR-0018 decision 6 needs to be true.
    """
    pending = unabsorbed_rules(rules, up_to_date_as_of=up_to_date_as_of, observed_on=observed_on)
    effective_dates = [as_date(rule.effective_on) for rule in pending]
    ages = [(observed_on - value).days for value in effective_dates if value is not None]
    return max(ages) if ages else 0


def pair_candidates(
    versions: Iterable[SectionVersion],
    rules: Sequence[FinalRule],
    *,
    tolerance_days: int = DEFAULT_PAIR_TOLERANCE_DAYS,
) -> tuple[Pairing, ...]:
    """Attribute each section-version to the closest plausible rule for its Part.

    ``basis`` records which rule date the lag was measured against: ``effective_on`` where the rule
    states one, else ``publication_date``. Mixing the two without saying which would make the
    resulting distribution unreadable.
    """
    pairings: list[Pairing] = []
    for version in versions:
        issued = as_date(version.issue_date)
        candidates: list[tuple[int, str, str]] = []
        if issued is not None and version.part is not None:
            for rule in rules:
                if version.part not in rule.parts:
                    continue
                anchor, basis = as_date(rule.effective_on), "effective_on"
                if anchor is None:
                    anchor, basis = as_date(rule.publication_date), "publication_date"
                if anchor is None:
                    continue
                delta = (issued - anchor).days
                if abs(delta) <= tolerance_days:
                    candidates.append((delta, rule.document_number, basis))
        candidates.sort(key=lambda c: (abs(c[0]), c[1]))
        best = candidates[0] if candidates else None
        pairings.append(
            Pairing(
                section=version.identifier,
                part=version.part,
                issue_date=version.issue_date,
                in_scope=version.in_scope,
                removed=version.removed,
                substantive=version.substantive,
                candidates=tuple(document for _, document, _ in candidates),
                absorption_lag_days=best[0] if best else None,
                basis=best[2] if best else None,
                ambiguous=len(candidates) > 1,
            )
        )
    return tuple(pairings)


# --- report over many observations --------------------------------------------------------


def load_observations(lines: Iterable[str]) -> tuple[list[dict[str, Any]], list[str]]:
    """Parse a JSONL log. Returns ``(observations, errors)`` — a bad line is reported, not fatal.

    A partially written line (the run was killed mid-redirect) must not discard a fortnight of
    good observations, so the loader reports it and continues.

    A leading BOM is stripped rather than reported. PowerShell's ``>>`` writes ``EF BB BF`` when it
    *creates* the target, so a log recreated on Windows would otherwise lose its first observation
    to a ``JSONDecodeError`` — a silent one-day loss discovered at day ten, if at all. Appending to
    an existing file adds no BOM, so this only bites after the file is deleted.
    """
    observations: list[dict[str, Any]] = []
    errors: list[str] = []
    for number, line in enumerate(lines, start=1):
        text = line.lstrip("﻿").strip()
        if not text:
            continue
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            errors.append(f"line {number}: not JSON ({exc})")
            continue
        if not isinstance(parsed, dict):
            errors.append(f"line {number}: expected an object, got {type(parsed).__name__}")
            continue
        observations.append(parsed)
    return observations, errors


def _spread(values: Sequence[int]) -> dict[str, Any]:
    if not values:
        return {"n": 0}
    ordered = sorted(values)
    return {
        "n": len(ordered),
        "min": ordered[0],
        "median": statistics.median(ordered),
        "max": ordered[-1],
    }


def summarize(observations: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Collapse many observations into the distributions ADR-0018 open question 1 asks for.

    A section-version is counted **once**, keyed by ``(section, issue_date)``, and a rule once by
    document number — consecutive runs re-read an overlapping window by design, so counting rows per
    observation would multiply one amendment by the number of days it stayed in the window. Getting
    this wrong would inflate every count by roughly the lookback length, which is exactly the kind
    of error that reads as a plausible distribution.
    """
    freshness = [
        int(o["freshness_lag_days"])
        for o in observations
        if isinstance(o.get("freshness_lag_days"), int)
    ]
    blind_spots = [
        int(o["blind_spot_days"]) for o in observations if isinstance(o.get("blind_spot_days"), int)
    ]
    ever_unabsorbed = {
        str(number) for o in observations for number in (o.get("unabsorbed_rules") or [])
    }

    absorption: dict[tuple[str, str], int] = {}
    basis_by_key: dict[tuple[str, str], str] = {}
    ambiguous: set[tuple[str, str]] = set()
    seen: set[tuple[str, str]] = set()
    in_scope_events: set[tuple[str, str]] = set()
    removed_events: set[tuple[str, str]] = set()
    for observation in observations:
        for pairing in observation.get("pairings", []) or []:
            key = (str(pairing.get("section")), str(pairing.get("issue_date")))
            seen.add(key)
            if pairing.get("in_scope"):
                in_scope_events.add(key)
            if pairing.get("removed"):
                removed_events.add(key)
            lag = pairing.get("absorption_lag_days")
            if isinstance(lag, int):
                absorption[key] = lag
                basis_by_key[key] = str(pairing.get("basis"))
                if pairing.get("ambiguous"):
                    ambiguous.add(key)
    # A later run may attribute what an earlier one could not — the rule can be published after the
    # section was issued. So "unattributed" is the set never attributed by *any* run, not per-run.
    unattributed = seen - set(absorption)
    bases = Counter(basis_by_key.values())

    leads: dict[str, int] = {}
    no_effective_date: set[str] = set()
    for observation in observations:
        for rule in observation.get("final_rules", []) or []:
            number = str(rule.get("document_number"))
            published = as_date(rule.get("publication_date"))
            effective = as_date(rule.get("effective_on"))
            if published is not None and effective is not None:
                leads[number] = (effective - published).days
            elif rule.get("effective_on") is None:
                no_effective_date.add(number)

    days_observed = sorted({str(o.get("observed_on")) for o in observations})
    return {
        "observations": len(observations),
        "days_observed": len(days_observed),
        "first_day": days_observed[0] if days_observed else None,
        "last_day": days_observed[-1] if days_observed else None,
        "freshness_lag_days": _spread(freshness),
        "blind_spot_days": _spread(blind_spots),
        "rules_ever_unabsorbed": sorted(ever_unabsorbed),
        "absorption_lag_days": _spread(list(absorption.values())),
        "absorption_basis": dict(bases),
        "ambiguous_attributions": len(ambiguous),
        "unattributed_section_versions": len(unattributed),
        "distinct_section_versions": len(absorption) + len(unattributed),
        "in_scope_section_versions": len(in_scope_events),
        "removed_section_versions": len(removed_events),
        "announcement_lead_days": _spread(list(leads.values())),
        "rules_without_effective_date": len(no_effective_date),
        "distinct_rules": len(leads) + len(no_effective_date),
        "truncated_observations": sum(
            1 for o in observations if any((o.get("truncated") or {}).values())
        ),
        "observations_with_notes": sum(1 for o in observations if o.get("notes")),
    }
