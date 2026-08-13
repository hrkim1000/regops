"""The six gates as data, and the Go/No-Go report that consolidates them.

A gate here is never a bare number. It carries the threshold it was compared against, the method
that produced it, and — the field that does the most work — ``measured``. A gate whose value could
not be measured is reported as **not measured**, never as a failure and never as a pass. Four of
six short calls No-Go, so silently coercing an unmeasured gate in either direction is the one
mistake that changes the decision.

Two failure modes the six gates do not catch travel with them as ``guards`` rather than as gates:
the "needs verification" rate (refuse everything → citation accuracy and hallucination rate both
pass) and alert precision (alert on everything → detection coverage and latency both pass). Neither
is gated in Phase 1; both belong in the report, because a gate set that can be satisfied by a
degenerate system is evidence of nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from regops_shared.constants import (
    CITATION_ACCURACY_FLOOR,
    DETECTION_COVERAGE_FLOOR,
    DETECTION_LATENCY_TARGET_HOURS,
    HALLUCINATION_RATE_CEILING,
    NO_GO_GATE_FAILURES,
    PILOT_RETENTION_FLOOR,
    RESEARCH_TIME_SAVING_FLOOR,
)


@dataclass(frozen=True, slots=True)
class Gate:
    """One of the six. ``ceiling`` inverts the comparison; everything else is a floor."""

    key: str
    label: str
    threshold: float
    method: str
    ceiling: bool = False
    unit: str = "share"


GATES: tuple[Gate, ...] = (
    Gate(
        key="detection_coverage",
        label="Detection coverage",
        threshold=DETECTION_COVERAGE_FLOOR,
        method=(
            "Share of actual amendments captured, verified by after-the-fact manual comparison. "
            "Scored against scheduled polls, with the uptime shortfall reported beside it"
        ),
    ),
    Gate(
        key="detection_latency",
        label="Detection latency",
        threshold=float(DETECTION_LATENCY_TARGET_HOURS),
        method="Authority publication → owner alert, worst case rather than mean",
        ceiling=True,
        unit="hours",
    ),
    Gate(
        key="citation_accuracy",
        label="Citation accuracy",
        threshold=CITATION_ACCURACY_FLOOR,
        method="Share of cited clauses that actually support the answer, blind RA assessment",
    ),
    Gate(
        key="hallucination_rate",
        label="Hallucination rate",
        threshold=HALLUCINATION_RATE_CEILING,
        method="Outputs citing non-existent clauses or contradicting source text",
        ceiling=True,
    ),
    Gate(
        key="research_time_saving",
        label="Research time savings",
        threshold=RESEARCH_TIME_SAVING_FLOOR,
        method="Versus the manual process for the same query type, against a pre-pilot baseline",
    ),
    Gate(
        key="pilot_retention",
        label="Pilot retention",
        threshold=PILOT_RETENTION_FLOOR,
        method="Voluntary use ≥ 1×/week for 4 consecutive weeks",
    ),
)

GATES_BY_KEY: dict[str, Gate] = {gate.key: gate for gate in GATES}


@dataclass(frozen=True, slots=True)
class GateResult:
    """One gate for one cell. ``value is None`` means not measured, which is its own verdict."""

    gate: Gate
    cell: str
    value: float | None
    #: What was actually run. A gate quoted without this cannot be reproduced or discounted.
    evidence: str
    #: Why it could not be measured, when it could not. Required in that case, and the renderer
    #: says so rather than leaving a blank cell that reads like a zero.
    unmeasured_reason: str | None = None
    caveats: list[str] = field(default_factory=list)

    @property
    def measured(self) -> bool:
        return self.value is not None

    @property
    def passed(self) -> bool | None:
        if self.value is None:
            return None
        return (
            self.value <= self.gate.threshold
            if self.gate.ceiling
            else self.value >= self.gate.threshold
        )

    @property
    def verdict(self) -> str:
        if self.passed is None:
            return "미측정"
        return "PASS" if self.passed else "FAIL"

    def render_value(self) -> str:
        if self.value is None:
            return "—"
        if self.gate.unit == "hours":
            return f"{self.value:.1f}h"
        return f"{self.value:.1%}"

    def render_threshold(self) -> str:
        prefix = "≤" if self.gate.ceiling else "≥"
        if self.gate.unit == "hours":
            return f"{prefix} {self.gate.threshold:.0f}h"
        return f"{prefix} {self.gate.threshold:.0%}"


@dataclass(frozen=True, slots=True)
class Guard:
    """A number reported beside the gates that is deliberately not one of them."""

    label: str
    value: float | None
    note: str
    unit: str = "share"

    def render_value(self) -> str:
        if self.value is None:
            return "—"
        return f"{self.value:.1%}" if self.unit == "share" else f"{self.value:g}"


@dataclass(frozen=True, slots=True)
class GoNoGoReport:
    generated_at: date
    regime: dict[str, str]
    results: list[GateResult]
    guards: list[Guard] = field(default_factory=list)
    deviations: list[tuple[str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    #: Two of the six gates are not cell-scoped. Pilot retention and research-time savings are
    #: measured over the pilot as a whole, so they carry this marker instead of a cell slug — and
    #: :meth:`recommendation` counts them against *every* cell rather than against none, which is
    #: what would happen if a shortfall were only ever matched by slug.
    UNSCOPED = "—"

    @property
    def cells(self) -> list[str]:
        return sorted({result.cell for result in self.results} - {self.UNSCOPED})

    @property
    def failures(self) -> list[GateResult]:
        return [result for result in self.results if result.passed is False]

    @property
    def unmeasured(self) -> list[GateResult]:
        return [result for result in self.results if not result.measured]

    @property
    def recommendation(self) -> str:
        """No-Go at four shortfalls **per cell** — a cell that misses is not offset by the other
        passing. An unmeasured gate is neither, so a report with any unmeasured gate cannot
        recommend anything yet and says so instead of guessing."""
        if self.unmeasured:
            return "INCOMPLETE"
        unscoped = sum(
            1 for result in self.results if result.cell == self.UNSCOPED and result.passed is False
        )
        for cell in self.cells:
            shortfalls = unscoped + sum(
                1 for result in self.results if result.cell == cell and result.passed is False
            )
            if shortfalls >= NO_GO_GATE_FAILURES:
                return "NO-GO"
        return "GO"


def render(report: GoNoGoReport) -> str:
    """Markdown, because the report is read by people and attached to a decision."""
    lines = [
        "# RegOps M4 Go/No-Go report",
        "",
        f"- **Generated:** {report.generated_at.isoformat()}",
        f"- **Recommendation:** **{report.recommendation}** "
        f"(No-Go at {NO_GO_GATE_FAILURES} shortfalls in any one cell)",
        "",
        "## Regime",
        "",
        "A score is only meaningful per regime. These are the versions the numbers below were "
        "produced at; a change to any of them invalidates them.",
        "",
        "| Key | Value |",
        "|---|---|",
    ]
    lines += [f"| `{key}` | `{value}` |" for key, value in sorted(report.regime.items())]

    lines += ["", "## The six gates, per cell", ""]
    for cell in report.cells:
        lines += [
            f"### `{cell}`",
            "",
            "| Gate | Threshold | Measured | Verdict | Method |",
            "|---|---|---|---|---|",
        ]
        for result in [row for row in report.results if row.cell == cell]:
            lines.append(
                f"| {result.gate.label} | {result.render_threshold()} | "
                f"{result.render_value()} | {result.verdict} | {result.gate.method} |"
            )
        lines.append("")
        for result in [row for row in report.results if row.cell == cell]:
            if result.unmeasured_reason:
                lines.append(f"> **{result.gate.label} — 미측정.** {result.unmeasured_reason}")
            for caveat in result.caveats:
                lines.append(f"> ⚠️ **{result.gate.label}.** {caveat}")
        lines.append("")

    if report.guards:
        lines += [
            "## Reported beside the gates, deliberately not gated",
            "",
            "A gate set that can be satisfied by a degenerate system is evidence of nothing. "
            "A system that refuses every question passes citation accuracy and hallucination rate "
            "cleanly; one that alerts on everything passes detection coverage and latency.",
            "",
            "| Number | Value | Why it is here |",
            "|---|---|---|",
        ]
        lines += [
            f"| {guard.label} | {guard.render_value()} | {guard.note} |" for guard in report.guards
        ]
        lines.append("")

    if report.unmeasured:
        lines += [
            "## Not measured",
            "",
            "Listed rather than defaulted. An unmeasured gate is not a pass and not a failure, "
            "and a report that guessed either way would be making the decision rather than "
            "informing it.",
            "",
        ]
        lines += [
            f"- **{result.gate.label}** (`{result.cell}`) — "
            f"{result.unmeasured_reason or 'no reason recorded'}"
            for result in report.unmeasured
        ]
        lines.append("")

    if report.deviations:
        lines += [
            "## Deviations, consolidated from every phase file",
            "",
            "| Phase | Deviation |",
            "|---|---|",
        ]
        lines += [f"| {phase} | {text} |" for phase, text in report.deviations]
        lines.append("")

    if report.notes:
        lines += ["## Notes", ""] + [f"- {note}" for note in report.notes] + [""]

    return "\n".join(lines)


def to_json(report: GoNoGoReport) -> dict[str, Any]:
    return {
        "generated_at": report.generated_at.isoformat(),
        "recommendation": report.recommendation,
        "regime": report.regime,
        "gates": [
            {
                "gate": result.gate.key,
                "cell": result.cell,
                "threshold": result.gate.threshold,
                "ceiling": result.gate.ceiling,
                "value": result.value,
                "measured": result.measured,
                "passed": result.passed,
                "evidence": result.evidence,
                "unmeasured_reason": result.unmeasured_reason,
                "caveats": result.caveats,
            }
            for result in report.results
        ],
        "guards": [
            {"label": guard.label, "value": guard.value, "note": guard.note}
            for guard in report.guards
        ],
        "deviations": [{"phase": phase, "text": text} for phase, text in report.deviations],
        "notes": report.notes,
    }


__all__ = [
    "GATES",
    "GATES_BY_KEY",
    "Gate",
    "GateResult",
    "GoNoGoReport",
    "Guard",
    "render",
    "to_json",
]
