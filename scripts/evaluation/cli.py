"""The evaluation harness entry point. Runs inside the stack, where the database and services are.

    docker compose exec -T -w /scripts regulation python -m evaluation.cli <command>

Commands, in the order a phase-1.6 run uses them::

    seed        propose a golden set from the clause store (never signs it)
    validate    composition, and every expected clause path resolved against the corpus
    run         ask every item, resumably, and record what came back
    score       score a recorded run — per axis, per domain, with the refusal rate beside it
    worksheet   emit the blind assessment worksheet, or read a filled one back
    polls       scheduled polls versus polls that ran — the uptime caveat
    determinism re-extract a fixed sample at the same regime and report drift
    gates       measure what can be measured and render the Go/No-Go report

Exit codes are meaningful: ``validate`` and ``score`` return non-zero on failure so either can gate
a release rather than only inform one.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from regops_shared.constants import Role
from regops_shared.db import sync_session

from . import cells as cells_config
from . import client, corpus, measure, report, seed, worksheet
from . import run as runner
from . import score as scoring
from .goldenset import GoldenSet, article_of, load, save, validate_composition

REPO = Path(__file__).resolve().parents[2]


def _eval_dir() -> Path:
    """Where the evaluation corpus lives, in the container and on a host, without a flag.

    Inside the stack ``docs/eval`` is mounted at ``/eval`` — the repo root is not, because a
    harness has no business editing an ADR. On a host with a ``.env``, the repo-relative path is
    right. ``REGOPS_EVAL_DIR`` overrides both, for a deployed stack that keeps the corpus elsewhere.
    """
    override = os.environ.get("REGOPS_EVAL_DIR")
    if override:
        return Path(override)
    mounted = Path("/eval")
    return mounted if mounted.is_dir() else REPO / "docs" / "eval"


EVAL_DIR = _eval_dir()
GOLDEN_DIR = EVAL_DIR / "golden"
GROUND_TRUTH_DIR = EVAL_DIR / "ground_truth"
RUNS_DIR = EVAL_DIR / "runs"


def cell_config() -> dict[str, cells_config.CellConfig]:
    """Which cells the harness measures, from ``docs/eval/cells.json``.

    Read through a function rather than bound at import: a module-level constant would be resolved
    before ``REGOPS_EVAL_DIR`` could point somewhere else, which is exactly how the map that used
    to live here went stale without anybody noticing.
    """
    return cells_config.for_dir(EVAL_DIR)


def configured_cells() -> list[str]:
    """Every cell the harness can be pointed at."""
    return sorted(cell_config())


def default_cells() -> list[str]:
    """The cells a command runs on when none is named — the **gated** ones.

    Not every configured cell. ``validate`` / ``run`` / ``score`` / ``gates`` are the phase 1.6 gate
    operations, and widening their default to four would quietly change what a documented command
    measures. A Phase 2 cell is opted into by name (``--cells fda_samd``) until it is gated, at
    which point the default follows the configuration on its own.
    """
    gated = [slug for slug, cell in cell_config().items() if cell.gated]
    return sorted(gated) or configured_cells()


#: Whose principal the harness acts as. A real ``users`` row, so ``queries.asked_by`` references a
#: person and the audit trail is not written by a synthetic id.
DEFAULT_EVAL_EMAIL = "ra@example.com"


def golden_path(cell: str) -> Path:
    return GOLDEN_DIR / f"{cell}.json"


def curated_path(cell: str) -> Path:
    return GOLDEN_DIR / f"{cell}.curated.json"


def artifact_path(cell: str) -> Path:
    return RUNS_DIR / f"{cell}.latest.json"


# --- commands ----------------------------------------------------------------------------------


def load_golden(cell: str) -> GoldenSet:
    """The cell's golden set, or an exit that says what is missing and how to make it.

    A configured cell is not a seeded one — the FDA cells are in ``cells.json`` and have no set yet.
    Letting that surface as a ``FileNotFoundError`` traceback would be the harness failing in the
    style it exists to prevent everywhere else.
    """
    path = golden_path(cell)
    if not path.exists():
        raise SystemExit(
            f"{cell}: no golden set at {path}. It is configured but not seeded — "
            f"run `seed --cells {cell}` first."
        )
    return load(path)


def cmd_seed(args: argparse.Namespace) -> int:
    with sync_session() as session:
        for cell in args.cells:
            target = golden_path(cell)
            existing = load(target) if target.exists() else None
            if existing and existing.ra_signed_off and not args.force:
                print(
                    f"{cell}: signed off by {existing.signed_off_by} — refusing to regenerate. "
                    f"After sign-off the JSON is the source of truth, not the generator.",
                    file=sys.stderr,
                )
                return 1
            built = seed.build(
                session,
                cell=cell,
                neighbour_cells=cell_config()[cell].neighbours,
                curated_path=curated_path(cell),
                set_version=args.set_version,
            )
            save(built, target)
            counts = ", ".join(
                f"{axis.value} {count}" for axis, count in built.axis_counts.items() if count
            )
            print(f"{cell}: {len(built.items)} items → {target} ({counts})")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    failed = False
    with sync_session() as session:
        registry = corpus.cells(session)
        for cell in args.cells:
            golden = load_golden(cell)
            composition = validate_composition(golden)
            index = corpus.article_index(session, registry[cell].id)
            everywhere = {article for articles in index.values() for article in articles}

            grounding: list[str] = []
            for item in golden.items:
                # A named document that is not in the cell is an authoring error. Without this the
                # lookup below falls back to "any article anywhere in the cell", and a typo in the
                # title would quietly widen the check instead of failing it.
                if item.expected_document and item.expected_document not in index:
                    grounding.append(
                        f"{item.id}: expected_document {item.expected_document!r} is not a "
                        f"document in {cell}"
                    )
                for path in item.expected_clause_paths:
                    article = article_of(path)
                    known = index.get(item.expected_document or "", set()) or everywhere
                    if article not in known:
                        grounding.append(
                            f"{item.id}: expected {path} — no {article} in "
                            f"{item.expected_document or 'this cell'}"
                        )
                for path in item.forbidden_clause_paths:
                    resolves = article_of(path) in (
                        index.get(item.expected_document or "", set()) or everywhere
                    )
                    if resolves and not item.notes:
                        grounding.append(
                            f"{item.id}: forbidden {path} exists and the item says nothing about "
                            f"why citing it is wrong — an unexplained trap is not reviewable"
                        )

            print(f"\n## {cell} — {composition.total} items")
            for axis, count in composition.axis_counts.items():
                print(f"  {axis.value:<15} {count}")
            for warning in composition.warnings:
                print(f"  ⚠️  {warning}")
            for error in [*composition.errors, *grounding]:
                print(f"  ❌ {error}")
            print(
                f"  → structurally valid: {composition.structurally_valid and not grounding}"
                f" · citable as gate evidence: {composition.citable and not grounding}"
            )
            failed = failed or bool(composition.errors) or bool(grounding)
    return 1 if failed else 0


def cmd_run(args: argparse.Namespace) -> int:
    # Everything the database is needed for happens here, before the model-bound part starts. A
    # session left open across a 40-minute run is closed by the server underneath it, which is how
    # the first full run died — after collecting every answer.
    with sync_session() as session:
        registry = {slug: row.id for slug, row in corpus.cells(session).items()}
        principal = corpus.user_id_for(session, args.email)
    if principal is None:
        print(f"no users row for {args.email}", file=sys.stderr)
        return 2

    services = client.connect(user_id=principal[0], email=args.email, role=Role(principal[1]))
    for cell in args.cells:
        golden = load_golden(cell)
        items = [item for item in golden.items if not args.axis or item.axis.value in args.axis]
        if args.per_axis:
            # A bare --limit takes the first N in id order, which is one axis' worth. A bounded
            # run that only asked identifier lookups would report a citation accuracy the full
            # set could not reproduce, which is the specific way a sample lies.
            taken: dict[str, int] = {}
            spread: list = []
            for item in items:
                if taken.get(item.axis.value, 0) < args.per_axis:
                    taken[item.axis.value] = taken.get(item.axis.value, 0) + 1
                    spread.append(item)
            items = spread
        print(f"{cell}: {len(items)} candidate item(s)")
        artifact = runner.execute(
            services,
            golden=golden,
            cell_id=registry[cell],
            artifact_path=artifact_path(cell),
            items=items,
            limit=args.limit,
        )
        print(f"{cell}: {len(artifact.observations)} observation(s) → {artifact_path(cell)}")
    return 0


def cmd_score(args: argparse.Namespace) -> int:
    lines: list[str] = []
    citable = True
    for cell in args.cells:
        golden = load_golden(cell)
        artifact = runner.RunArtifact.load(artifact_path(cell))
        if artifact is None:
            print(f"{cell}: no run artifact — run first", file=sys.stderr)
            return 2
        # A run that died before its resolution pass leaves citations nobody looked up. Resolving
        # here rather than scoring them as unresolved: an unchecked citation is not a fabricated
        # one, and the difference is a 100% hallucination rate invented by the harness.
        pending = runner.unresolved_citations(artifact)
        if pending:
            print(f"{cell}: resolving {pending} unchecked citation(s) against the corpus")
            runner.resolve_citations(artifact)
            artifact.save(artifact_path(cell))
        result = scoring.score_queries(cell, golden.items, runner.observations_from(artifact))
        citable = citable and golden.ra_signed_off
        lines.append(_render_score(cell, golden, artifact, result))
    text = "\n".join(lines)
    print(text)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    return 0 if citable else 1


def _render_score(
    cell: str, golden: GoldenSet, artifact: runner.RunArtifact, result: scoring.QueryScore
) -> str:
    def pct(value: float | None) -> str:
        return "—" if value is None else f"{value:.1%}"

    lines = [
        f"# Scored run — `{cell}`",
        "",
        f"- **Run:** `{artifact.run_id}` started {artifact.started_at}",
        f"- **Golden set:** {golden.set_version}, "
        f"{'RA-signed' if golden.ra_signed_off else '**NOT RA-signed**'}",
        f"- **Scored:** {result.scored_items} of {len(golden.items)} item(s) — "
        f"{result.harness_errors} harness error(s) and {result.not_attempted} never asked, both "
        f"excluded from every rate below",
        "",
        "## Regime",
        "",
        "| Key | Value |",
        "|---|---|",
    ]
    lines += [f"| `{key}` | `{value}` |" for key, value in sorted(artifact.regime.items())]
    lines += [
        "",
        "## Per axis",
        "",
        "A single headline would let identifier lookups carry the hard axes. Outcome accuracy is "
        "'did it answer when it should and refuse when it should'.",
        "",
        "| Axis | Scored / in set | Outcome accuracy | Answers | Refusals | Citations | Resolving "
        "| Expected-path match | Trap citations | States 시행일 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for axis, block in result.per_axis.items():
        lines.append(
            f"| {axis.value} | {block.scored} / {block.items} | "
            f"{pct(block.outcome_accuracy)} | {block.answers} | "
            f"{block.refusals} | {block.citations} | {pct(block.citation_resolvable)} | "
            f"{pct(block.citation_expected_match)} | {block.trap_citations} | "
            f"{pct(block.scope_statement_rate)} |"
        )
    overall = result.overall
    lines += [
        "",
        "## Overall",
        "",
        f"- **Answer rate:** {pct(result.answer_rate)} · "
        f"**refusal rate:** {pct(result.refusal_rate)}",
        "",
        "  Reported first on purpose. A system that refuses everything scores perfectly on",
        "  citation accuracy and hallucination rate, so those two gates are not self-guarding,",
        "  and this pair is what keeps them honest.",
        "",
        f"- **Citation accuracy (lower bound):** {pct(overall.citation_expected_match)} — "
        f"{overall.citations_expected}/{overall.citations} citations named a clause the set "
        f"expected. **This is not the gate.** A generation may cite a different clause that also "
        f"supports the claim; the gate is the blind RA assessment, and this is the number that "
        f"says whether one is worth running.",
        f"- **Hallucination (mechanical half):** {pct(overall.hallucination_nonexistent)} — "
        f"{overall.hallucinating_answers}/{overall.answers} answers cited a clause that resolves "
        f"to nothing at the version named, or a path the set forbids. The other half — "
        f"contradicting the source text — is a reading and comes back from the worksheet.",
        f"- **Citations resolving:** {pct(overall.citation_resolvable)}",
        "",
    ]
    if result.misses:
        lines += [
            "## Wrong outcome, first 25",
            "",
            ", ".join(f"`{item}`" for item in result.misses[:25]),
            "",
        ]
    if not golden.ra_signed_off:
        lines += [
            "> ⚠️ **This run is not gate evidence.** The golden set is not RA-signed, so these "
            "numbers measure the harness against a set the system's own authors proposed.",
            "",
        ]
    return "\n".join(lines)


def cmd_worksheet(args: argparse.Namespace) -> int:
    if args.read:
        rows = worksheet.read(Path(args.read))
        assessment = scoring.score_assessment(rows)
        print(
            json.dumps(
                {
                    "assessed_citations": assessment.assessed_citations,
                    "citation_accuracy": assessment.citation_accuracy,
                    "answers_assessed": assessment.answers_assessed,
                    "contradiction_rate": assessment.contradiction_rate,
                },
                indent=2,
            )
        )
        return 0

    with sync_session() as session:
        for cell in args.cells:
            artifact = runner.RunArtifact.load(artifact_path(cell))
            if artifact is None:
                print(f"{cell}: no run artifact", file=sys.stderr)
                return 2
            golden = load_golden(cell)
            rows, used = worksheet.build(
                session,
                artifact,
                questions={item.id: item.question for item in golden.items},
                seed=args.seed,
            )
            target = EVAL_DIR / "worksheets" / f"{cell}.assessment.csv"
            worksheet.write(rows, target, seed=used, run_id=artifact.run_id)
            print(f"{cell}: {len(rows)} row(s) → {target} (seed {used})")
    return 0


def cmd_sample(args: argparse.Namespace) -> int:
    """Draw the blind clause sample the IR ground-truth markup is written against.

    Blind means the *selection criterion* touches nothing the extractor produced. This draws from
    ``clauses`` alone, by a recorded seed, and never looks at ``irs`` — so the denominator is fixed
    before either the RA or the extractor is consulted, and a clause cannot be dropped later for
    having turned out to be hard. That is the only protection left: the markup was meant to run in
    parallel with phase 1.2 and did not, so it will be written while a working extractor exists.
    """
    GROUND_TRUTH_DIR.mkdir(parents=True, exist_ok=True)
    with sync_session() as session:
        registry = corpus.cells(session)
        for cell in args.cells:
            versions = corpus.in_force_versions(session, registry[cell].id)
            title = args.document or next(
                (name for name in versions if name in {"화장품법", "의료기기법"}), None
            )
            if title is None or title not in versions:
                print(f"{cell}: no in-force version for {title!r}", file=sys.stderr)
                return 2
            version = versions[title]
            paths = [path for path, _ in corpus.articles(session, version.id)]
            drawn = sorted(random.Random(args.seed).sample(paths, min(args.size, len(paths))))

            sample_file = GROUND_TRUTH_DIR / f"{cell}.atomicity_sample.json"
            sample_file.write_text(
                json.dumps(drawn, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            template = GROUND_TRUTH_DIR / f"{cell}.ir_markup.template.json"
            template.write_text(
                json.dumps(
                    {
                        "_instructions": (
                            "Read each clause and write how many atomic obligations it yields "
                            "under the ADR-0004 decision 1 rule. Write 0 for a definition or a "
                            "clause bearing no duty — omitting a path is an error, because "
                            "'I judged this to yield nothing' and 'I did not look at it' are the "
                            "distinction ADR-0004 decision 6 exists to keep. Mark up from the "
                            "clause text alone: never from /irs or /coverage output."
                        ),
                        "document_version_id": str(version.id),
                        "document": title,
                        "domain": registry[cell].domain,
                        "rater": "REPLACE-WITH-YOUR-NAME",
                        "marked_at": "YYYY-MM-DD",
                        "sample": drawn,
                        "clauses": dict.fromkeys(drawn),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            print(
                f"{cell}: {len(drawn)} clause(s) from {title} @ {version.effective_date} "
                f"(seed {args.seed}) → {sample_file.name}, {template.name}"
            )
            _submission_template(session, cell=cell, versions=versions, parent=title)
    return 0


def _submission_template(session, *, cell: str, versions: dict, parent: str) -> None:
    """The submission-detection markup sheet: every 조 of the cell's 시행규칙, unmarked.

    Deliberately **not** pre-filled with what the detector found. Pre-filling would anchor the RA
    on the detector's answer, and the number this sheet produces is precisely how often the
    detector is wrong — a loose first pattern matched 341 clauses, a strict one 92, and the
    committed one yields 102–103 with nobody having confirmed which is right (phase1.5 deviation
    6). Marking against the detector's own output could not tell those three apart.
    """
    # The 시행규칙 of the instrument the atomicity sample was drawn from, so both markup exercises
    # sit in the same statutory family. Falling back to any 시행규칙 would have the RA marking
    # 디지털의료제품법 시행규칙 while the extraction sample came from 의료기기법.
    title = f"{parent} 시행규칙"
    if title not in versions:
        title = next((name for name in sorted(versions) if name.endswith("시행규칙")), "")
    if not title:
        return
    version = versions[title]
    rows = corpus.articles(session, version.id)
    target = GROUND_TRUTH_DIR / f"{cell}.submission_sample.template.json"
    target.write_text(
        json.dumps(
            {
                "_instructions": (
                    "For each clause below, decide whether it states a filing duty whose 각 호 "
                    "are the documents to be submitted. Move its clause_path into "
                    "procedure_clause_paths. Leave a 기준 list, a definition or a substantive "
                    "requirement out. Do not consult the /submission-requirements endpoint: this "
                    "sheet is the denominator its precision is measured against."
                ),
                "versions": [
                    {
                        "label": f"{title} @ {version.effective_date}",
                        "document_version_id": str(version.id),
                        "procedure_clause_paths": [],
                    }
                ],
                "candidates": [{"clause_path": path, "heading": heading} for path, heading in rows],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"{cell}: {len(rows)} candidate clause(s) from {title} → {target.name}")


def cmd_polls(args: argparse.Namespace) -> int:
    with sync_session() as session:
        shortfall = measure.poll_shortfall(session, days=args.days)
    print(shortfall.caveat)
    if shortfall.worst:
        print("\nWorst shortfalls (source, due, ran):")
        for label, due, ran in shortfall.worst:
            print(f"  {ran:>5} / {due:<5}  {label}")
    return 0


def cmd_determinism(args: argparse.Namespace) -> int:
    version_id = uuid.UUID(args.version_id)
    with sync_session() as session:
        runs = corpus.extraction_runs(session, version_id, args.domain, limit=2)
        if len(runs) < 2:
            print(
                "Fewer than two completed extraction runs for this version and domain. Trigger a "
                "second with POST /api/v1/document-versions/{id}/extract, then re-run.",
                file=sys.stderr,
            )
            return 2
        (newer_id, newer_regime), (older_id, older_regime) = runs
        if newer_regime != older_regime:
            print(
                f"Regimes differ ({newer_regime} vs {older_regime}). Drift between regimes is an "
                f"expected change, not a determinism defect — re-run at a matched triple.",
                file=sys.stderr,
            )
            return 2
        result = scoring.score_determinism(
            triple=newer_regime,
            first=corpus.ir_counts_for_run(session, older_id),
            second=corpus.ir_counts_for_run(session, newer_id),
        )
    print(
        f"Regime: {result.triple}\n"
        f"Clauses compared: {result.clauses}\n"
        f"IRs: {result.first_total} → {result.second_total}\n"
        f"Drift rate: "
        f"{'—' if result.drift_rate is None else f'{result.drift_rate:.2%}'} "
        f"({result.drifted_clauses} clause(s) changed count)\n"
        "\nTemperature 0 is greedy decoding, not determinism. This is the measured drift, not an "
        "assertion of zero: batching, quantization and a provider-side model update all move "
        "output, and a claim of zero that nobody measured is worse than a measured small number."
    )
    return 0


def cmd_gates(args: argparse.Namespace) -> int:
    ledger = measure.load_json(GROUND_TRUTH_DIR / "amendment_ledger.json")
    cohort = measure.load_json(GROUND_TRUTH_DIR / "pilot_cohort.json") or {}
    baseline = measure.load_json(GROUND_TRUTH_DIR / "research_time_baseline.json")

    results: list[report.GateResult] = []
    guards: list[report.Guard] = []
    notes: list[str] = []

    with sync_session() as session:
        principal = corpus.user_id_for(session, args.email)
        if principal is None:
            print(f"no users row for {args.email}", file=sys.stderr)
            return 2
        services = client.connect(user_id=principal[0], email=args.email, role=Role(principal[1]))

        shortfall = measure.poll_shortfall(session, days=args.days)
        alerts = client.alert_metrics(services, days=args.days)
        answers = client.answer_metrics(services)

        for cell in args.cells:
            results.append(
                measure.detection_coverage(
                    session, cell=cell, days=args.days, shortfall=shortfall, ledger=ledger
                )
            )
            results.append(measure.detection_latency(alerts, cell=cell))
            results.extend(_answer_gates(cell))

        results.append(measure.retention(session, cohort=list(cohort.get("users") or [])))
        results.append(_time_saving_gate(baseline))

        for row in answers.get("domains", []):
            guards.append(
                report.Guard(
                    label=f"'확인 필요' rate — {row['domain']}",
                    value=row.get("needs_verification_rate"),
                    note=(
                        "Two-sided. Near 0% means the confidence threshold is too permissive and "
                        "the hallucination gate is about to be missed; too high means the product "
                        "is unusable however honest it is (ADR-0006 decision 7)."
                    ),
                )
            )
        for row in alerts.get("cells", []):
            guards.append(
                report.Guard(
                    label=f"Alert volume — {row['cell']}",
                    value=float(row["alerts"]),
                    note=(
                        f"{row['change_events_alerted']} of {row['change_events_emitted']} change "
                        f"events alerted to {row['subscribers']} subscriber(s). Alert *precision* "
                        f"is not gated in Phase 1: a system that alerted on everything would pass "
                        f"detection coverage and latency cleanly."
                    ),
                    unit="count",
                )
            )
        guards.append(
            report.Guard(
                label="Scheduled-poll completion",
                value=shortfall.coverage.poll_completion,
                note=(
                    "Not a gate, and the reason the coverage gate is scored against scheduled "
                    "polls: a day the poller did not run leaves no observation row at all, so an "
                    "observed-poll denominator makes downtime improve the number."
                ),
            )
        )

    notes.append(
        "Three gates are human judgements and the harness does not fill them in: citation "
        "accuracy and the contradiction half of hallucination rate come from the blind worksheet, "
        "and research-time savings needs a baseline captured before the pilot starts."
    )
    built = report.GoNoGoReport(
        generated_at=datetime.now(UTC).date(),
        regime=runner.static_regime(),
        results=results,
        guards=guards,
        deviations=_deviations(),
        notes=notes,
    )
    rendered = report.render(built)
    print(rendered)
    if args.out:
        target = Path(args.out)
        target.write_text(rendered, encoding="utf-8")
        target.with_suffix(".json").write_text(
            json.dumps(report.to_json(built), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return 0


def _answer_gates(cell: str) -> list[report.GateResult]:
    """Citation accuracy and hallucination rate, from a scored run plus a filled worksheet."""
    artifact = runner.RunArtifact.load(artifact_path(cell))
    assessment_path = EVAL_DIR / "worksheets" / f"{cell}.assessment.csv"
    accuracy = report.GATES_BY_KEY["citation_accuracy"]
    hallucination = report.GATES_BY_KEY["hallucination_rate"]

    if artifact is None:
        reason = "No scored run for this cell."
        return [
            report.GateResult(
                gate=accuracy, cell=cell, value=None, evidence="—", unmeasured_reason=reason
            ),
            report.GateResult(
                gate=hallucination, cell=cell, value=None, evidence="—", unmeasured_reason=reason
            ),
        ]

    golden = load_golden(cell)
    scored = scoring.score_queries(cell, golden.items, runner.observations_from(artifact))
    unsigned = (
        ""
        if golden.ra_signed_off
        else " The golden set is not RA-signed, so this run is not gate evidence."
    )

    try:
        rows = worksheet.read(assessment_path) if assessment_path.exists() else []
    except ValueError as exc:
        rows = []
        unsigned += f" Worksheet unusable: {exc}"

    if not rows:
        mechanical = scored.overall.hallucination_nonexistent
        return [
            report.GateResult(
                gate=accuracy,
                cell=cell,
                value=None,
                evidence=(
                    f"lower bound {scored.overall.citations_expected}/"
                    f"{scored.overall.citations} citations matched an expected clause"
                ),
                unmeasured_reason=(
                    "No completed blind assessment. Whether a clause *supports* a claim is a "
                    "reading, and the expected-path match is a lower bound, not the gate."
                    + unsigned
                ),
            ),
            report.GateResult(
                gate=hallucination,
                cell=cell,
                value=None,
                evidence=(
                    f"mechanical half: {scored.overall.hallucinating_answers}/"
                    f"{scored.overall.answers} answers cited a non-existent or forbidden clause "
                    f"({'—' if mechanical is None else f'{mechanical:.1%}'})"
                ),
                unmeasured_reason=(
                    "The contradiction half needs the blind assessment. Reporting the mechanical "
                    "half alone as the gate would understate it by exactly the failures the "
                    "verification agent exists to catch." + unsigned
                ),
            ),
        ]

    assessment = scoring.score_assessment(rows)
    combined = scoring.hallucination_rate(
        answers=scored.overall.answers,
        fabricated_citation_answers=scored.overall.hallucinating_answers,
        contradicting_answers=assessment.answers_contradicting,
    )
    caveats = [] if golden.ra_signed_off else ["Golden set is not RA-signed; not gate evidence."]
    return [
        report.GateResult(
            gate=accuracy,
            cell=cell,
            value=assessment.citation_accuracy,
            evidence=(
                f"{assessment.supporting}/{assessment.assessed_citations} cited clauses judged to "
                f"support their claim, blind assessment"
            ),
            caveats=caveats,
        ),
        report.GateResult(
            gate=hallucination,
            cell=cell,
            value=combined,
            evidence=(
                f"{scored.overall.hallucinating_answers} answer(s) cited a non-existent or "
                f"forbidden clause; {assessment.answers_contradicting} judged to contradict the "
                f"source, over {scored.overall.answers} answers"
            ),
            caveats=caveats,
        ),
    ]


def _time_saving_gate(baseline: Any) -> report.GateResult:
    gate = report.GATES_BY_KEY["research_time_saving"]
    if not baseline:
        return report.GateResult(
            gate=gate,
            cell=report.GoNoGoReport.UNSCOPED,
            value=None,
            evidence="—",
            unmeasured_reason=(
                "No pre-pilot baseline. The manual time for matched query types has to be captured "
                "before the pilot starts, or the 30% is unfalsifiable."
            ),
        )
    value = scoring.time_saving(
        baseline_minutes=float(baseline["baseline_minutes"]),
        measured_minutes=float(baseline["measured_minutes"]),
    )
    return report.GateResult(
        gate=gate,
        cell=report.GoNoGoReport.UNSCOPED,
        value=value,
        evidence=(
            f"{baseline['measured_minutes']} min against a {baseline['baseline_minutes']} min "
            f"baseline over {baseline.get('query_types', '?')} matched query type(s)"
        ),
    )


def _deviations() -> list[tuple[str, str]]:
    """Every phase file's deviation headings, consolidated.

    Read from the files rather than restated: a hand-copied list is stale the first time a phase
    file gains a deviation, and this list is what makes an M4 report writable at all.
    """
    out: list[tuple[str, str]] = []
    for path in sorted((REPO / "docs" / "plan").glob("phase*.md")):
        section = False
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("## "):
                section = line.strip().lower().startswith("## deviations")
                continue
            if not section:
                continue
            stripped = line.strip()
            if stripped.startswith(("**", "1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.")):
                out.append((path.stem, stripped[:200]))
    return out


# --- wiring ------------------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="evaluation", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    def with_cells(node: argparse.ArgumentParser) -> argparse.ArgumentParser:
        node.add_argument("--cells", nargs="+", default=default_cells(), choices=configured_cells())
        return node

    seed_cmd = with_cells(sub.add_parser("seed", help="propose a golden set from the clause store"))
    seed_cmd.add_argument("--set-version", default="1.0.0")
    seed_cmd.add_argument(
        "--force", action="store_true", help="regenerate even if the set is RA-signed"
    )
    seed_cmd.set_defaults(func=cmd_seed)

    with_cells(sub.add_parser("validate", help="composition and corpus grounding")).set_defaults(
        func=cmd_validate
    )

    run_cmd = with_cells(sub.add_parser("run", help="ask every item, resumably"))
    run_cmd.add_argument("--limit", type=int, help="stop after N unanswered items")
    run_cmd.add_argument("--axis", nargs="+", help="restrict to these axes")
    run_cmd.add_argument(
        "--per-axis", type=int, help="take at most N items per axis — a bounded run that spreads"
    )
    run_cmd.add_argument("--email", default=DEFAULT_EVAL_EMAIL)
    run_cmd.set_defaults(func=cmd_run)

    score_cmd = with_cells(sub.add_parser("score", help="score a recorded run"))
    score_cmd.add_argument("--out", help="also write the markdown here")
    score_cmd.set_defaults(func=cmd_score)

    sheet = with_cells(sub.add_parser("worksheet", help="blind assessment worksheet"))
    sheet.add_argument("--seed", type=int, default=1606, help="recorded shuffle seed")
    sheet.add_argument("--read", help="read a filled worksheet back instead of emitting one")
    sheet.set_defaults(func=cmd_worksheet)

    sample = with_cells(sub.add_parser("sample", help="draw the blind IR ground-truth sample"))
    sample.add_argument("--size", type=int, default=40)
    sample.add_argument("--seed", type=int, default=1606, help="recorded, so the draw is auditable")
    sample.add_argument("--document", help="instrument title; defaults to 화장품법 / 의료기기법")
    sample.set_defaults(func=cmd_sample)

    polls = sub.add_parser("polls", help="scheduled polls versus polls that ran")
    polls.add_argument("--days", type=int, default=30)
    polls.set_defaults(func=cmd_polls)

    determinism = sub.add_parser("determinism", help="IR drift between two runs at one regime")
    determinism.add_argument("--version-id", required=True)
    determinism.add_argument("--domain", required=True, choices=["samd", "cosmetic"])
    determinism.set_defaults(func=cmd_determinism)

    gates = with_cells(sub.add_parser("gates", help="measure and render the Go/No-Go report"))
    gates.add_argument("--days", type=int, default=30)
    gates.add_argument("--email", default=DEFAULT_EVAL_EMAIL)
    gates.add_argument("--out", help="also write the report here")
    gates.set_defaults(func=cmd_gates)

    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
