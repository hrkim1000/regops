"""Entry point for the eCFR-versus-Federal-Register lag measurement.

Runs inside the stack, where ``PoliteFetcher`` and its settings live::

    E="docker compose exec -T -w /scripts regulation python -m fda_lag.cli"

    # once a day for a fortnight — append-only, one JSON object per line
    $E probe >> docs/design/fda-lag-observations.jsonl

    # any time: the distributions, from the log piped back in
    $E report < docs/design/fda-lag-observations.jsonl

``docs/`` is not mounted into the service container, so the log is written by redirecting on the
host and read by piping back through ``exec -T`` — the same trade ``admrul_triage.py`` makes, and it
avoids a mount that only this measurement would use.

**``report`` exits non-zero until the sample is large enough to answer the question.** The number it
produces would otherwise get quoted as the answer after three days, and the whole reason this exists
is that one observation is not a distribution. Same discipline as the phase-1.6 harness reporting
``미측정`` rather than defaulting a gate.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, date, datetime
from typing import Any

from fda_lag.probe import (
    DEFAULT_LOOKBACK_DAYS,
    DEFAULT_PAIR_TOLERANCE_DAYS,
    ProbeError,
    load_observations,
    summarize,
)

#: Distinct days required before ``report`` will state a verdict. A fortnight of weekdays — the
#: window ADR-0018 open question 1 asks for, minus the weekends the Federal Register does not
#: publish on.
DEFAULT_MIN_DAYS: int = 10

#: Blind spot, in days, at or below which the eCFR can carry the detection gate. One day is the
#: floor the endpoint's own granularity allows: ``up_to_date_as_of`` is a date, not a timestamp, so
#: no arrangement of these calls resolves below it.
GATE_BLIND_SPOT_DAYS: int = 1


def _render(summary: dict[str, Any], *, min_days: int, errors: list[str]) -> str:
    fresh = summary["freshness_lag_days"]
    blind = summary["blind_spot_days"]
    absorb = summary["absorption_lag_days"]
    lead = summary["announcement_lead_days"]
    enough = summary["days_observed"] >= min_days

    out: list[str] = [
        "# eCFR versus Federal Register — measured lag",
        "",
        f"- **Observations:** {summary['observations']} over "
        f"{summary['days_observed']} distinct days "
        f"({summary['first_day']} → {summary['last_day']})",
        "- **Closes:** ADR-0018 open question 1 — *how far does the eCFR `versions` endpoint lag "
        "the Federal Register?*",
        "",
    ]

    if not enough:
        out += [
            f"> **UNDETERMINED — {summary['days_observed']} of {min_days} days.** The numbers "
            "below are real but the sample is not yet a distribution. Do not quote this as the "
            "answer; keep running `probe` daily.",
            "",
        ]

    out += [
        "## The lag that bounds the detection gate",
        "",
        "**Blind spot** — days since the oldest rule that is *in force* yet absent from the "
        "compilation. Zero means every rule in force is present, which is what ADR-0018 decision 6 "
        "needs to be true. This is the verdict input.",
        "",
        "| n | min | median | max |",
        "|---:|---:|---:|---:|",
        f"| {blind.get('n', 0)} | {blind.get('min', '—')} | {blind.get('median', '—')} "
        f"| {blind.get('max', '—')} |",
        "",
        "**Raw freshness** — observation date minus the title's own `up_to_date_as_of`. Context "
        "only: it cannot tell a compilation that is *behind* from one that did not advance because "
        "**nothing was amended**, and those are opposite findings with the same number.",
        "",
        "| n | min | median | max |",
        "|---:|---:|---:|---:|",
        f"| {fresh.get('n', 0)} | {fresh.get('min', '—')} | {fresh.get('median', '—')} "
        f"| {fresh.get('max', '—')} |",
        "",
    ]

    if enough and blind.get("n"):
        unabsorbed = summary["rules_ever_unabsorbed"]
        if blind["max"] <= GATE_BLIND_SPOT_DAYS:
            out += [
                f"**The eCFR can carry the gate.** Across {blind['n']} observations no rule was "
                f"ever in force while absent from the compilation for more than {blind['max']} "
                "day(s), so polling `versions/title-21.json` sees an amendment within the window "
                "ADR-0018 decision 6 assumes.",
                "",
                "Day granularity is the endpoint's, not the measurement's — `up_to_date_as_of` is "
                "a date, so this bounds the lag at ≤1 day and cannot *prove* ≤24h. That is the "
                "strongest claim this surface supports, and it is the claim the ADR needs.",
            ]
        else:
            out += [
                f"**The eCFR alone cannot carry the gate.** The blind spot reached "
                f"{blind['max']} days (median {blind['median']}): rules were in force and absent "
                "from the compilation for longer than the ≤24h detection-latency gate allows. "
                "ADR-0018 decision 6 makes the eCFR the primary detection surface; on this "
                "evidence that decision needs revisiting, with the Federal Register carrying "
                "detection and the eCFR carrying citation.",
                "",
                f"Rules observed in force but unabsorbed: {', '.join(unabsorbed) or '—'}",
            ]
        out.append("")

    out += [
        "## Absorption — how long after a rule bites does the text show it",
        "",
        "eCFR `issue_date` - the rule's `effective_on` (or `publication_date` where the rule "
        "states none). Attribution is by Part plus date proximity, never by citation string: the "
        "eCFR sources part 820 to `89 FR 7523` while the Federal Register calls the same rule "
        "`89 FR 7496`.",
        "",
        "| n | min | median | max |",
        "|---:|---:|---:|---:|",
        f"| {absorb.get('n', 0)} | {absorb.get('min', '—')} | {absorb.get('median', '—')} "
        f"| {absorb.get('max', '—')} |",
        "",
        f"- Distinct section-versions seen: **{summary['distinct_section_versions']}**, "
        f"of which **{summary['in_scope_section_versions']}** touched a Part the FDA cells claim",
        f"- Flagged `removed` by the authority: **{summary['removed_section_versions']}**",
        f"- Could not be attributed to any rule: **{summary['unattributed_section_versions']}**",
        f"- Attributed but ambiguous (more than one candidate rule): "
        f"**{summary['ambiguous_attributions']}**",
        f"- Attribution basis: {summary['absorption_basis'] or '—'}",
        "",
        "## Announcement lead — how much warning the authority gives",
        "",
        "`effective_on` - `publication_date`. Not a lag in our pipeline: ADR-0018 decision 7 says "
        "a pending amendment produces no version, so this is the size of that blind spot.",
        "",
        "| n | min | median | max |",
        "|---:|---:|---:|---:|",
        f"| {lead.get('n', 0)} | {lead.get('min', '—')} | {lead.get('median', '—')} "
        f"| {lead.get('max', '—')} |",
        "",
        f"- Rules seen: **{summary['distinct_rules']}**, of which "
        f"**{summary['rules_without_effective_date']}** stated no effective date "
        "(ADR-0013 applies — null, with the phrase retained)",
        "",
        "## Data health",
        "",
        f"- Observations carrying a note: **{summary['observations_with_notes']}**",
        f"- Observations where a response was truncated: **{summary['truncated_observations']}**",
    ]
    if errors:
        out += ["", "**Unreadable log lines:**", ""]
        out += [f"- {message}" for message in errors]
    out.append("")
    return "\n".join(out)


def _force_utf8() -> None:
    """Both streams carry non-ASCII, and the default console encoding may not.

    The container is UTF-8; a Windows host console is not — it is cp949 here, which raised
    ``UnicodeEncodeError`` on the first em dash of the report. The probe path needs this too:
    ``to_json`` uses ``ensure_ascii=False``, so one non-ASCII character in a rule title would kill
    a day's observation on the same console. Guarded because ``sys.stdout`` is not always a
    ``TextIOWrapper`` — pytest replaces it.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")


def _observed_on(raw: str) -> date:
    """An ISO date within a day of the container's own, or an error.

    The bound is the guard, not the parsing. A timezone can move the operator's calendar day by at
    most one either way — UTC+14 to UTC-12 — so anything further out is a typo or a stale shell
    variable, and a typo here does not fail loudly: it files a real observation under the wrong day
    and quietly corrupts a ten-day series that has no way to notice.
    """
    try:
        value = date.fromisoformat(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{raw!r} is not an ISO date (YYYY-MM-DD)") from exc
    drift = abs((value - datetime.now(UTC).date()).days)
    if drift > 1:
        raise argparse.ArgumentTypeError(
            f"{raw} is {drift} days from the container's UTC date — no timezone is that far off, "
            "so this is a typo rather than a local date"
        )
    return value


def main(argv: list[str] | None = None) -> int:
    _force_utf8()
    parser = argparse.ArgumentParser(prog="fda_lag.cli", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    probe_cmd = sub.add_parser("probe", help="one observation, as a JSON line on stdout")
    probe_cmd.add_argument("--lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS)
    probe_cmd.add_argument("--tolerance-days", type=int, default=DEFAULT_PAIR_TOLERANCE_DAYS)
    probe_cmd.add_argument(
        "--observed-on",
        type=_observed_on,
        default=None,
        metavar="YYYY-MM-DD",
        help=(
            "calendar day to file this observation under; defaults to the container's UTC date. "
            "The wrapper passes the operator's local date, because the series counts distinct "
            "days and a day means the operator's day (see fetch.observe)."
        ),
    )

    report_cmd = sub.add_parser("report", help="distributions over a JSONL log read from stdin")
    report_cmd.add_argument("--min-days", type=int, default=DEFAULT_MIN_DAYS)

    args = parser.parse_args(argv)

    if args.command == "probe":
        # Imported here, not at the top: `fetch` resolves only inside a service container, and
        # `report` must stay runnable on the host — where the same import would fail.
        import structlog

        from fda_lag.fetch import PoliteFetcher, observe

        # **stdout is data.** `PoliteFetcher` logs a warning per retryable status, and structlog's
        # unconfigured default sink is stdout — which put two `fetch.retryable_status` lines into
        # the JSONL log on the first live run. Redirect the sink before anything can fetch.
        # `load_observations` also tolerates a stray non-JSON line, so this is the fix and that is
        # the backstop.
        structlog.configure(logger_factory=structlog.PrintLoggerFactory(file=sys.stderr))

        try:
            with PoliteFetcher() as fetcher:
                observation = observe(
                    fetcher,
                    observed_on=args.observed_on,
                    lookback_days=args.lookback_days,
                    tolerance_days=args.tolerance_days,
                )
        except ProbeError as exc:
            print(f"probe failed: {exc}", file=sys.stderr)
            return 2
        print(observation.to_json())
        for note in observation.notes:
            print(f"note: {note}", file=sys.stderr)
        print(
            f"observed {observation.observed_on}: freshness "
            f"{observation.freshness_lag_days} day(s), "
            f"{len(observation.section_versions)} section-versions, "
            f"{len(observation.final_rules)} final rules since {observation.lookback_from}",
            file=sys.stderr,
        )
        return 0

    observations, errors = load_observations(sys.stdin)
    if not observations:
        print("report: no observations on stdin", file=sys.stderr)
        return 2
    summary = summarize(observations)
    sys.stdout.write(_render(summary, min_days=args.min_days, errors=errors))
    if summary["days_observed"] < args.min_days:
        print(
            f"UNDETERMINED — {summary['days_observed']} of {args.min_days} days observed",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
