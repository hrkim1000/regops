"""The measurements that do not need a model: coverage, latency, submissions, retention, extraction.

Each one returns a :class:`~scripts.evaluation.report.GateResult` or a scored dataclass, and each
one is explicit about the difference between *the system's own account* and *what actually
happened*. That distinction is the difference between a measurement and a self-assessment, and it
is where two of the six gates live:

- **Detection coverage** is the share of the authority's actual amendments that were captured. The
  system can report how many amendments it *saw*; it cannot report how many it missed. Without an
  RA-supplied amendment ledger the gate is returned unmeasured, with the system-side number and the
  poll shortfall attached as caveats — never as the gate.
- **Detection latency** is measurable from stored clocks, and is reported from both of them, with
  the alerts that carry no publication date counted as unmeasurable rather than as zero.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from regops_shared.constants import PILOT_RETENTION_WEEKS

from . import client, corpus, score
from .client import Services
from .report import GATES_BY_KEY, GateResult, GoNoGoReport


@dataclass(frozen=True, slots=True)
class PollShortfall:
    coverage: score.PollCoverage
    #: Sources that produced fewer observations than their interval implies, worst first. The list
    #: is the actionable half: "94% of scheduled polls ran" says nothing about which source is dark.
    worst: list[tuple[str, int, int]]

    @property
    def caveat(self) -> str:
        completion = self.coverage.poll_completion
        if completion is None:
            return "No enabled schedule in the window — poll completion is undefined."
        return (
            f"Poll completion {completion:.1%}: {self.coverage.observed_polls} of "
            f"{self.coverage.expected_polls} scheduled polls ran over "
            f"{self.coverage.window_days:.0f} "
            f"days across {self.coverage.sources} sources ({self.coverage.shortfall} missed). "
            f"Detection coverage measured over observed polls would have divided by the polls that "
            f"happened rather than the polls that were due, and downtime would have improved it."
        )


def poll_shortfall(session: Session, *, days: int) -> PollShortfall:
    """Scheduled polls versus polls that ran. The uptime caveat the coverage gate travels with."""
    window_end = datetime.now(UTC)
    window_start = window_end - timedelta(days=days)

    expected = observed = sources = 0
    worst: list[tuple[str, int, int]] = []
    for row in corpus.schedules_with_observations(session, days=days):
        if not row.enabled:
            continue
        # A source registered mid-window was not due for the whole window. Crediting it with polls
        # it could not have run would manufacture a shortfall out of ordinary onboarding.
        created = row.created_at if row.created_at.tzinfo else row.created_at.replace(tzinfo=UTC)
        effective_start = max(window_start, created)
        window_seconds = max((window_end - effective_start).total_seconds(), 0.0)
        due = score.expected_polls(
            window_seconds=window_seconds, interval_seconds=row.interval_seconds
        )
        sources += 1
        expected += due
        observed += row.observations
        if row.observations < due:
            worst.append((row.label, due, row.observations))

    worst.sort(key=lambda entry: entry[2] - entry[1])
    return PollShortfall(
        coverage=score.PollCoverage(
            window_days=days,
            sources=sources,
            expected_polls=expected,
            observed_polls=observed,
        ),
        worst=worst[:10],
    )


def detection_coverage(
    session: Session,
    *,
    cell: str,
    days: int,
    shortfall: PollShortfall,
    ledger: dict[str, list[str]] | None,
) -> GateResult:
    """Share of the authority's actual amendments that were captured.

    The denominator has to come from outside the system. ``ledger`` is the RA's after-the-fact list
    of what the authority actually published in the window; without it this returns unmeasured and
    attaches what the system saw as a caveat, because "we detected everything we detected" is 100%
    by construction and is not the gate.
    """
    gate = GATES_BY_KEY["detection_coverage"]
    seen = corpus.amendment_versions(session, cell, days=days)
    caveats = [shortfall.caveat]

    expected = ledger.get(cell) if ledger else None
    if not expected:
        return GateResult(
            gate=gate,
            cell=cell,
            value=None,
            evidence=f"{len(seen)} amended versions detected in the last {days} days",
            unmeasured_reason=(
                "No RA amendment ledger for this cell. The denominator is what the authority "
                "actually published, which only after-the-fact manual comparison can supply — "
                "the system's own count of what it saw would score 100% by construction. Author "
                "docs/eval/ground_truth/amendment_ledger.json to measure this."
            ),
            caveats=caveats,
        )

    detected = [entry for entry in expected if entry in seen]
    missed = sorted(set(expected) - seen)
    if missed:
        caveats.append(f"Missed: {', '.join(missed[:10])}")
    return GateResult(
        gate=gate,
        cell=cell,
        value=len(detected) / len(expected),
        evidence=(
            f"{len(detected)}/{len(expected)} ledger amendments detected over {days} days "
            f"(ledger authored by RA, compared after the fact)"
        ),
        caveats=caveats,
    )


def detection_latency(metrics: dict[str, Any], *, cell: str) -> GateResult:
    """Publication → alert, worst case, from the authority's clock where it stated one.

    ``max`` rather than a mean, because the gate is a ceiling: a mean that hid one 40-hour outlier
    behind ninety fast ones would report a pass on a run that failed.
    """
    gate = GATES_BY_KEY["detection_latency"]
    block = next((row for row in metrics.get("cells", []) if row["cell"] == cell), None)
    if block is None:
        return GateResult(
            gate=gate,
            cell=cell,
            value=None,
            evidence="no alerts in the window",
            unmeasured_reason="No alert was raised for this cell in the measurement window.",
        )

    latency = block["latency_hours"]
    published, retrieved = latency["from_published"], latency["from_retrieved"]
    backfill = latency.get("backfill", 0)
    worst_ours = retrieved["max"] if retrieved["max"] is not None else "—"
    caveats: list[str] = []
    if latency["unmeasurable"]:
        caveats.append(
            f"{latency['unmeasurable']} alert(s) carry no authority publication date, so their "
            f"latency is unmeasurable rather than zero (ADR-0003 decision 5). Worst case from our "
            f"own retrieval clock: {worst_ours}h."
        )
    if backfill:
        caveats.append(
            f"{backfill} alert(s) cover amendments published before this cell came under "
            f"observation ({latency.get('watching_since') or '?'}) and are excluded: publication → "
            f"alert on a backfilled corpus measures how long the instrument existed before RegOps "
            f"arrived, not how fast RegOps noticed."
        )
    if published["count"] == 0:
        return GateResult(
            gate=gate,
            cell=cell,
            value=None,
            evidence=(
                f"{block['alerts']} alert(s) in the window, none of them measurable: "
                f"{backfill} backfill, {latency['unmeasurable']} with no publication date"
            ),
            unmeasured_reason=(
                "No alert in the window covers an amendment published while this cell was under "
                "observation, so there is nothing the gate can be measured on yet. Latency from "
                "our own retrieval clock — worst case "
                f"{worst_ours}h — bounds our pipeline, not the gate. This resolves itself: the "
                "first amendment published after ingestion started is measurable."
            ),
            caveats=caveats,
        )
    return GateResult(
        gate=gate,
        cell=cell,
        value=float(published["max"]),
        evidence=(
            f"worst of {published['count']} alert(s) with a publication date; "
            f"{published['within_target']} within target"
        ),
        caveats=caveats,
    )


def submission_detection(
    services: Services, *, sample: dict[str, Any]
) -> list[score.BinaryDetection]:
    """Submission-requirement detection precision and recall against an RA-marked sample.

    Scored per document version, never pooled: the pattern's precision is a property of the
    instrument's drafting style, and one 고시 that lists 기준 in the shape of a document list would
    be averaged away against a well-behaved 시행규칙.
    """
    results: list[score.BinaryDetection] = []
    for entry in sample.get("versions", []):
        version_id = uuid.UUID(str(entry["document_version_id"]))
        marked = list(entry.get("procedure_clause_paths") or [])
        detected = [
            row["clause_path"] for row in client.submission_requirements(services, version_id)
        ]
        results.append(
            score.score_detection(
                label=str(entry.get("label") or version_id), marked=marked, detected=detected
            )
        )
    return results


def extraction_against_markup(
    session: Session, *, markup: dict[str, Any]
) -> tuple[score.ExtractionScore, str]:
    """Extraction precision, recall and citation correctness against blind RA markup.

    Returns the score and the regime triple the extraction ran at. The triple is not decoration:
    the markup is blind to *an* extractor run, and comparing it against a different regime's output
    measures two changes at once.
    """
    version_id = uuid.UUID(str(markup["document_version_id"]))
    domain = str(markup["domain"])
    sample = list(markup["sample"])
    marked = {str(key): int(value) for key, value in markup["clauses"].items()}

    extracted = corpus.ir_counts(session, version_id, domain)
    citations, resolving = corpus.ir_citation_resolution(session, version_id)
    run = corpus.latest_extraction_run(session, version_id, domain)
    triple = run or "no extraction run recorded for this version and domain"
    return (
        score.score_extraction(
            sample=sample,
            marked=marked,
            extracted=extracted,
            citations=citations,
            citations_resolving=resolving,
        ),
        triple,
    )


def retention(
    session: Session, *, cohort: list[str], weeks: int = PILOT_RETENTION_WEEKS
) -> GateResult:
    """Voluntary weekly use across four consecutive weeks, from ``queries``.

    A pilot that has not run yet is unmeasured, not 0% — the two look identical in a rate and mean
    opposite things.
    """
    gate = GATES_BY_KEY["pilot_retention"]
    weekly = corpus.weekly_query_users(session, weeks=weeks)
    result = score.score_retention(cohort=cohort, weekly_users=weekly, weeks=weeks)
    if not cohort:
        return GateResult(
            gate=gate,
            cell=GoNoGoReport.UNSCOPED,
            value=None,
            evidence=f"weekly active: {result.weekly_active}",
            unmeasured_reason=(
                "No pilot cohort recorded. Retention needs 20–30 onboarded users and four "
                "uncompressible weeks of real use; a rate computed over an empty cohort is not a "
                "small number, it is no number."
            ),
        )
    return GateResult(
        gate=gate,
        cell="—",
        value=result.rate,
        evidence=(
            f"{result.retained} of {result.cohort} used it every week for {weeks} consecutive "
            f"weeks; weekly active {result.weekly_active}"
        ),
    )


def load_json(path: Path) -> Any | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


__all__ = [
    "PollShortfall",
    "detection_coverage",
    "detection_latency",
    "extraction_against_markup",
    "load_json",
    "poll_shortfall",
    "retention",
    "submission_detection",
]
