"""Measure whether the atomicity rule is operative, not advisory.

    docker compose exec -T regulation python //scripts/ir_agreement.py \
        --sample docs/eval/atomicity_sample.json rater_a.json rater_b.json

ADR-0004 decision 1 replaced "one atomic regulatory obligation" with a written rule because two
reviewers reading the same clause would otherwise produce different IR counts, making every
downstream count — coverage, gap, impact — non-comparable between people and between extraction
runs. A written rule is worth no more than an unwritten one unless somebody checks that two readers
applying it land in the same place. That is what this measures.

**Phase 1 staffs one RA** (development-plan.md § 7, risk 7), so the criterion as written — inter-
rater agreement — is not runnable as written. The recorded decision (phase1.2 § Deviations, 3) is to
degrade to **same-rater test–retest at ≥ 2 weeks' separation** until a second rater is funded, and
to say so rather than to quietly relabel one rater's two passes as two raters' agreement. The script
takes two markup files either way and reports which mode it ran in, because the two answer different
questions:

``inter-rater``
    Two people, one rule. Detects an *ambiguous rule* — the thing the ADR was written to remove.

``test-retest``
    One person, twice, ≥ 2 weeks apart. Detects an unstable rule and an unstable reader, but **not**
    a reader's consistent private interpretation of an ambiguous rule: the same misreading returns
    both times and scores as perfect agreement. A high test–retest score is therefore a necessary
    condition, never a sufficient one, and this script says so in its own output so a Go/No-Go
    report cannot cite the number without the caveat.

## Markup format

Each rater file is JSON: ``{"rater": "...", "marked_at": "YYYY-MM-DD", "clauses": {...}}`` where
``clauses`` maps ``clause_path`` → the number of IRs that clause yields under the rule. A rater who
believes a clause is a definition writes ``0``; omitting it is an error, because "I judged this to
yield nothing" and "I did not look at it" are the distinction ADR-0004 decision 6 exists to keep.

Extractor output can stand in for one side via ``--from-db <version_id> <domain>``, which is how the
same script answers "does the agent agree with the RA" — but note that a run compared against the
markup it was tuned on measures nothing. Ground-truth markup must be built **blind** to extractor
output (phase1.6), and this script cannot enforce that; it can only refuse to pretend otherwise.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

#: Below this, the rule is not operative and the finding is escalated rather than worked around.
#: Krippendorff's convention for content analysis; the same threshold the evaluation slice uses.
AGREEMENT_FLOOR = 0.80

#: Test–retest is only meaningful with enough separation that the rater is applying the rule again
#: rather than recalling their earlier answer.
MIN_RETEST_DAYS = 14


@dataclass(frozen=True, slots=True)
class Markup:
    rater: str
    marked_at: date | None
    counts: dict[str, int]

    @classmethod
    def load(cls, path: Path) -> Markup:
        payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        raw = payload.get("clauses")
        if not isinstance(raw, dict) or not raw:
            raise SystemExit(f"{path}: 'clauses' must be a non-empty object of path → IR count")
        marked = payload.get("marked_at")
        return cls(
            rater=str(payload.get("rater") or path.stem),
            marked_at=date.fromisoformat(marked) if marked else None,
            counts={str(k): int(v) for k, v in raw.items()},
        )


@dataclass(frozen=True, slots=True)
class Agreement:
    mode: str
    sample_size: int
    exact_agreement: float
    mean_abs_delta: float
    total_a: int
    total_b: int
    disagreements: list[tuple[str, int, int]]
    warnings: list[str]

    @property
    def passes(self) -> bool:
        return self.sample_size > 0 and self.exact_agreement >= AGREEMENT_FLOOR


def compare(a: Markup, b: Markup, *, sample: list[str] | None = None) -> Agreement:
    """Score two markups over the clauses they share, or over an explicit sample.

    Restricting to the intersection would let a rater raise the score by skipping the clauses they
    found hard, so an explicit ``--sample`` is the honest way to run this: the denominator is fixed
    before either rater starts, and a missing clause counts as a disagreement rather than vanishing.
    """
    warnings: list[str] = []
    paths = sample if sample is not None else sorted(set(a.counts) & set(b.counts))

    if sample is None:
        only_a = set(a.counts) - set(b.counts)
        only_b = set(b.counts) - set(a.counts)
        if only_a or only_b:
            warnings.append(
                f"scored over the {len(paths)} shared clauses; "
                f"{len(only_a)} marked only by {a.rater} and {len(only_b)} only by {b.rater} were "
                f"dropped — pass --sample to fix the denominator instead"
            )

    missing = [path for path in paths if path not in a.counts or path not in b.counts]
    if missing:
        warnings.append(
            f"{len(missing)} sample clause(s) unmarked by at least one rater; counted as 0 and as "
            f"a disagreement — an unmarked clause is not the same as a clause judged to yield none"
        )

    mode = _mode(a, b, warnings)

    exact = 0
    deltas: list[int] = []
    disagreements: list[tuple[str, int, int]] = []
    for path in paths:
        left = a.counts.get(path, 0)
        right = b.counts.get(path, 0)
        deltas.append(abs(left - right))
        if left == right and path not in missing:
            exact += 1
        else:
            disagreements.append((path, left, right))

    return Agreement(
        mode=mode,
        sample_size=len(paths),
        exact_agreement=exact / len(paths) if paths else 0.0,
        mean_abs_delta=statistics.fmean(deltas) if deltas else 0.0,
        total_a=sum(a.counts.get(path, 0) for path in paths),
        total_b=sum(b.counts.get(path, 0) for path in paths),
        disagreements=sorted(disagreements, key=lambda row: -abs(row[1] - row[2])),
        warnings=warnings,
    )


def _mode(a: Markup, b: Markup, warnings: list[str]) -> str:
    """Which question this run answers. Never inferred generously."""
    if a.rater != b.rater:
        return "inter-rater"

    if a.marked_at and b.marked_at:
        separation = abs((a.marked_at - b.marked_at).days)
        if separation < MIN_RETEST_DAYS:
            warnings.append(
                f"test-retest separated by {separation} days, under the {MIN_RETEST_DAYS}-day "
                f"floor — the second pass may be recall rather than re-application"
            )
    else:
        warnings.append("test-retest with no marked_at on both files; separation unverifiable")

    warnings.append(
        "TEST-RETEST, NOT INTER-RATER: this cannot detect a rater's consistent private reading of "
        "an ambiguous rule. A passing score here is necessary, not sufficient (phase1.2 § "
        "Deviations, 3)"
    )
    return "test-retest"


def render(result: Agreement) -> str:
    lines = [
        "# IR atomicity agreement",
        "",
        f"- **Mode:** {result.mode}",
        f"- **Sample:** {result.sample_size} clauses",
        f"- **Exact agreement on IR count:** {result.exact_agreement:.1%} "
        f"(floor {AGREEMENT_FLOOR:.0%}) — {'PASS' if result.passes else 'FAIL'}",
        f"- **Mean absolute delta:** {result.mean_abs_delta:.2f} IRs per clause",
        f"- **Total IRs:** {result.total_a} vs {result.total_b}",
        "",
    ]
    for warning in result.warnings:
        lines.append(f"> ⚠️ {warning}")
    if result.warnings:
        lines.append("")

    if result.disagreements:
        lines += [
            "## Disagreements, widest first",
            "",
            "| clause_path | A | B |",
            "|---|---:|---:|",
        ]
        lines += [f"| `{path}` | {left} | {right} |" for path, left, right in result.disagreements]
    else:
        lines.append("No disagreements.")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("markup", nargs=2, type=Path, help="two rater markup JSON files")
    parser.add_argument(
        "--sample",
        type=Path,
        help="JSON list of clause_paths fixing the denominator before either rater starts",
    )
    args = parser.parse_args(argv)

    a, b = (Markup.load(path) for path in args.markup)
    sample = json.loads(args.sample.read_text(encoding="utf-8")) if args.sample else None
    if sample is not None and not isinstance(sample, list):
        raise SystemExit("--sample must be a JSON list of clause paths")

    result = compare(a, b, sample=sample)
    sys.stdout.write(render(result))
    # Non-zero on failure so this can gate a release rather than only inform one.
    return 0 if result.passes else 1


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
