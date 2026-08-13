"""The scoring math, as pure functions over plain data. No database, no network, no clock.

Everything the Go/No-Go report divides lives here, for one reason: a bug in this file produces a
*passing* gate, and a passing gate is not investigated. Separating the arithmetic from the I/O is
what makes it testable at all — every function below is exercised by ``tests/test_score.py``
against hand-built inputs whose right answer was worked out by hand.

Three of the numbers here are deliberately named for what they are rather than for the gate they
feed:

``citation_expected_match``
    A **lower bound** on citation accuracy. It counts a citation as good when its 조 is one the RA
    recorded, and a generation is free to cite a *different* clause that also supports the claim.
    The gate is the blind assessment; this is the number that tells you whether to bother running
    one.

``hallucination_nonexistent``
    The **mechanically checkable half** of the hallucination gate: a citation that resolves to no
    clause at the version it names. The other half — contradicting the source text — is a reading,
    and it comes back from the worksheet.

``clause_level_precision`` / ``clause_level_recall``
    **Upper bounds** on extraction precision and recall. Ground-truth markup records how many
    obligations a clause yields, not which ones, so an extractor that finds the right *number* of
    the wrong obligations scores perfectly here. It is the number the markup format can support;
    calling it precision without the qualifier would overstate what was measured.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from regops_shared.constants import EvaluationAxis, ExpectedOutcome

from .goldenset import GoldenItem, article_of

# --- query scoring -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ObservedCitation:
    """One citation an answer carried, with the one fact only the corpus can supply."""

    document_version_id: str
    clause_path: str
    #: Does a clause exist at this path in this version? False is a fabrication, full stop —
    #: not a disagreement about relevance.
    resolves: bool


@dataclass(frozen=True, slots=True)
class ObservedAnswer:
    """What running one golden item actually produced."""

    item_id: str
    #: ``answered`` | ``needs_verification`` | ``needs_review``, verbatim from ``answers.status``.
    status: str
    citations: tuple[ObservedCitation, ...] = ()
    no_answer_reason: str | None = None
    confidence: float | None = None
    elapsed_seconds: float | None = None
    #: The effective date the answer says it relied on (ADR-0006 decision 8). ``None`` means the
    #: answer stated no version at all, which the effective-date axis exists to catch.
    effective_date_scope: str | None = None
    straddles_effective_date: bool = False
    #: Set when the run itself failed (timeout, transport). Distinct from a refusal: the system
    #: declining is a product outcome, the harness giving up is not, and averaging them together
    #: is how an infrastructure failure reads as an honest refusal.
    error: str | None = None

    @property
    def produced_answer(self) -> bool:
        return self.error is None and self.status == ExpectedOutcome.ANSWERED.value

    @property
    def refused(self) -> bool:
        # `needs_review` is a refusal for scoring: sub-threshold confidence does not reach the
        # reader as final, so treating it as an answer would credit the system with an answer
        # nobody was given.
        return self.error is None and not self.produced_answer


@dataclass(frozen=True, slots=True)
class AxisScore:
    axis: EvaluationAxis
    items: int
    errors: int
    outcome_correct: int
    answers: int
    refusals: int
    citations: int
    citations_resolving: int
    citations_expected: int
    hallucinating_answers: int
    trap_citations: int
    #: Items in the set that this run never asked. Not a failure — see :class:`QueryScore`.
    not_attempted: int = 0
    #: Answers that stated the effective date they relied on. Reported per axis because it is the
    #: effective-date axis' real subject: an answer that names no version looks identical to one
    #: that does, and a reader acts on both the same way.
    answers_stating_scope: int = 0

    @property
    def scope_statement_rate(self) -> float | None:
        return self.answers_stating_scope / self.answers if self.answers else None

    @property
    def scored(self) -> int:
        """Items this run actually got an outcome for. The denominator of every rate below."""
        return self.items - self.errors - self.not_attempted

    @property
    def outcome_accuracy(self) -> float | None:
        return self.outcome_correct / self.scored if self.scored else None

    @property
    def citation_expected_match(self) -> float | None:
        return self.citations_expected / self.citations if self.citations else None

    @property
    def citation_resolvable(self) -> float | None:
        return self.citations_resolving / self.citations if self.citations else None

    @property
    def hallucination_nonexistent(self) -> float | None:
        return self.hallucinating_answers / self.answers if self.answers else None


@dataclass(frozen=True, slots=True)
class QueryScore:
    """One cell's scored run, whole and per axis."""

    cell: str
    scored_items: int
    harness_errors: int
    #: Items with no observation at all. Distinct from a harness error on purpose: a bounded run
    #: deliberately leaves most of the set unasked, and counting those as failures would report a
    #: broken harness every time somebody ran a sample.
    not_attempted: int
    per_axis: dict[EvaluationAxis, AxisScore]
    overall: AxisScore
    #: Items whose outcome was wrong, for the report's shortlist. A rate with no examples beside it
    #: is not actionable.
    misses: list[str] = field(default_factory=list)

    @property
    def answer_rate(self) -> float | None:
        return self.overall.answers / self.overall.scored if self.overall.scored else None

    @property
    def refusal_rate(self) -> float | None:
        return self.overall.refusals / self.overall.scored if self.overall.scored else None


def score_queries(
    cell: str,
    items: Sequence[GoldenItem],
    observed: Mapping[str, ObservedAnswer],
) -> QueryScore:
    """Score a run over three buckets, because there are three things that can happen to an item.

    **Scored** — asked, answered or refused. **Harness error** — asked, and the harness never got
    an answer back. **Not attempted** — never asked, which is what most of a bounded run is.

    None of the three may be folded into another. An error read as a refusal moves the refusal
    rate, the number that keeps the citation and hallucination gates honest, in the direction that
    looks healthy. A not-attempted item read as an error reports a broken harness every time
    somebody runs a sample — and a not-attempted item read as *scored* would be worse still, since
    it would enter the denominator of an accuracy it was never part of.
    """
    buckets: dict[EvaluationAxis, list[tuple[GoldenItem, ObservedAnswer | None]]] = defaultdict(
        list
    )
    for item in items:
        buckets[item.axis].append((item, observed.get(item.id)))

    misses: list[str] = []
    per_axis: dict[EvaluationAxis, AxisScore] = {}
    for axis, pairs in buckets.items():
        per_axis[axis] = _score_axis(axis, pairs, misses)

    overall = _merge(EvaluationAxis.IDENTIFIER, per_axis.values())
    return QueryScore(
        cell=cell,
        scored_items=overall.items - overall.errors - overall.not_attempted,
        harness_errors=overall.errors,
        not_attempted=overall.not_attempted,
        per_axis=dict(sorted(per_axis.items(), key=lambda row: row[0].value)),
        overall=overall,
        misses=sorted(misses),
    )


def _score_axis(
    axis: EvaluationAxis,
    pairs: Sequence[tuple[GoldenItem, ObservedAnswer | None]],
    misses: list[str],
) -> AxisScore:
    errors = unattempted = outcome_correct = answers = refusals = 0
    citations = resolving = expected_match = hallucinating = traps = scoped = 0

    for item, answer in pairs:
        if answer is None:
            unattempted += 1
            continue
        if answer.error is not None:
            errors += 1
            continue

        if answer.produced_answer:
            answers += 1
            if answer.effective_date_scope:
                scoped += 1
        else:
            refusals += 1

        if answer.produced_answer is not item.expects_refusal:
            outcome_correct += 1
        else:
            misses.append(item.id)

        wanted = {article_of(path) for path in item.expected_clause_paths}
        forbidden = {article_of(path) for path in item.forbidden_clause_paths}
        fabricated = False
        for citation in answer.citations:
            citations += 1
            article = article_of(citation.clause_path)
            if citation.resolves:
                resolving += 1
            else:
                fabricated = True
            if article in wanted:
                expected_match += 1
            if article in forbidden:
                traps += 1
                # A trap path was proven not to resolve when the set was validated, so citing one
                # is a fabrication even if this run's resolution lookup somehow disagreed.
                fabricated = True
        if fabricated and answer.produced_answer:
            hallucinating += 1

    return AxisScore(
        axis=axis,
        items=len(pairs),
        errors=errors,
        outcome_correct=outcome_correct,
        answers=answers,
        refusals=refusals,
        citations=citations,
        citations_resolving=resolving,
        citations_expected=expected_match,
        hallucinating_answers=hallucinating,
        trap_citations=traps,
        not_attempted=unattempted,
        answers_stating_scope=scoped,
    )


def _merge(axis: EvaluationAxis, scores: Iterable[AxisScore]) -> AxisScore:
    rows = list(scores)
    return AxisScore(
        axis=axis,
        items=sum(row.items for row in rows),
        errors=sum(row.errors for row in rows),
        outcome_correct=sum(row.outcome_correct for row in rows),
        answers=sum(row.answers for row in rows),
        refusals=sum(row.refusals for row in rows),
        citations=sum(row.citations for row in rows),
        citations_resolving=sum(row.citations_resolving for row in rows),
        citations_expected=sum(row.citations_expected for row in rows),
        hallucinating_answers=sum(row.hallucinating_answers for row in rows),
        trap_citations=sum(row.trap_citations for row in rows),
        not_attempted=sum(row.not_attempted for row in rows),
        answers_stating_scope=sum(row.answers_stating_scope for row in rows),
    )


# --- blind assessment --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AssessedCitation:
    """One RA judgement, read back from a completed worksheet."""

    item_id: str
    claim_index: int
    clause_path: str
    #: Does the cited clause support the claim? The citation-accuracy gate is this and nothing else.
    supports: bool
    #: Does the answer contradict the cited source text? The other half of the hallucination gate.
    contradicts: bool = False


@dataclass(frozen=True, slots=True)
class BlindAssessment:
    assessed_citations: int
    supporting: int
    answers_assessed: int
    answers_contradicting: int

    @property
    def citation_accuracy(self) -> float | None:
        """The gate. Share of cited clauses that actually support the answer."""
        return self.supporting / self.assessed_citations if self.assessed_citations else None

    @property
    def contradiction_rate(self) -> float | None:
        return self.answers_contradicting / self.answers_assessed if self.answers_assessed else None


def score_assessment(rows: Sequence[AssessedCitation]) -> BlindAssessment:
    answers = {row.item_id for row in rows}
    contradicting = {row.item_id for row in rows if row.contradicts}
    return BlindAssessment(
        assessed_citations=len(rows),
        supporting=sum(1 for row in rows if row.supports),
        answers_assessed=len(answers),
        answers_contradicting=len(contradicting),
    )


def hallucination_rate(
    *, answers: int, fabricated_citation_answers: int, contradicting_answers: int
) -> float | None:
    """The gate, both halves. An answer counted once however many ways it went wrong.

    Union rather than sum: an answer that cites a non-existent clause *and* contradicts the text is
    one bad answer, and adding the two counts could push the rate above 1.0 — a number that would
    quietly discredit the whole report.
    """
    if not answers:
        return None
    # The two sets are not tracked per answer id here, so the honest combination is the widest
    # possible overlap: at least as many bad answers as the larger of the two, at most their sum.
    bad = max(fabricated_citation_answers, contradicting_answers)
    return min(bad, answers) / answers


# --- extraction --------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ExtractionScore:
    sample_clauses: int
    marked_irs: int
    extracted_irs: int
    matched_irs: int
    citations: int
    citations_resolving: int
    #: Clauses the RA marked as bearing obligations where the extractor produced none. The
    #: gap-analysis pillar's evidence base is exactly this number.
    missed_clauses: list[str] = field(default_factory=list)
    #: Clauses the RA marked as bearing none where the extractor produced some.
    invented_clauses: list[str] = field(default_factory=list)

    @property
    def clause_level_precision(self) -> float | None:
        return self.matched_irs / self.extracted_irs if self.extracted_irs else None

    @property
    def clause_level_recall(self) -> float | None:
        return self.matched_irs / self.marked_irs if self.marked_irs else None

    @property
    def citation_correctness(self) -> float | None:
        return self.citations_resolving / self.citations if self.citations else None


def score_extraction(
    *,
    sample: Sequence[str],
    marked: Mapping[str, int],
    extracted: Mapping[str, int],
    citations: int = 0,
    citations_resolving: int = 0,
) -> ExtractionScore:
    """Count-level agreement over a denominator fixed before either side ran.

    ``sample`` is the denominator and it is passed in rather than derived from the keys: scoring
    over the intersection would let a clause nobody marked and nobody extracted vanish, and a
    clause the RA skipped count as agreement.
    """
    matched = marked_total = extracted_total = 0
    missed: list[str] = []
    invented: list[str] = []
    for path in sample:
        left = marked.get(path, 0)
        right = extracted.get(path, 0)
        marked_total += left
        extracted_total += right
        matched += min(left, right)
        if left and not right:
            missed.append(path)
        if right and not left:
            invented.append(path)
    return ExtractionScore(
        sample_clauses=len(sample),
        marked_irs=marked_total,
        extracted_irs=extracted_total,
        matched_irs=matched,
        citations=citations,
        citations_resolving=citations_resolving,
        missed_clauses=sorted(missed),
        invented_clauses=sorted(invented),
    )


@dataclass(frozen=True, slots=True)
class DeterminismScore:
    """Temperature 0 is greedy decoding, not determinism. This reports drift; it never asserts
    zero, because batching, quantization and a provider-side model update all move output and a
    claim of zero that nobody measured is worse than a measured small number."""

    triple: str
    clauses: int
    drifted_clauses: int
    first_total: int
    second_total: int

    @property
    def drift_rate(self) -> float | None:
        return self.drifted_clauses / self.clauses if self.clauses else None


def score_determinism(
    *, triple: str, first: Mapping[str, int], second: Mapping[str, int]
) -> DeterminismScore:
    paths = sorted(set(first) | set(second))
    return DeterminismScore(
        triple=triple,
        clauses=len(paths),
        drifted_clauses=sum(1 for path in paths if first.get(path, 0) != second.get(path, 0)),
        first_total=sum(first.values()),
        second_total=sum(second.values()),
    )


# --- detection coverage ------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PollCoverage:
    """The uptime caveat that has to travel beside the detection-coverage gate.

    Coverage computed over *observations* divides by the polls that happened rather than the polls
    that were due, so downtime silently improves it. Observed for real on 2026-08-04: 28
    observations on 08-03, 16 on 08-05, none on 08-04 while the stack was down.
    """

    window_days: float
    sources: int
    expected_polls: int
    observed_polls: int

    @property
    def poll_completion(self) -> float | None:
        return self.observed_polls / self.expected_polls if self.expected_polls else None

    @property
    def shortfall(self) -> int:
        return max(self.expected_polls - self.observed_polls, 0)


def expected_polls(*, window_seconds: float, interval_seconds: int) -> int:
    """Polls due for one source over a window. Floor, so a partial interval is not credited."""
    if interval_seconds <= 0:
        return 0
    return int(window_seconds // interval_seconds)


@dataclass(frozen=True, slots=True)
class DetectionCoverage:
    cell: str
    amendments_expected: int
    amendments_detected: int

    @property
    def coverage(self) -> float | None:
        return (
            self.amendments_detected / self.amendments_expected
            if self.amendments_expected
            else None
        )


# --- submission-requirement detection ------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BinaryDetection:
    """False positives and false negatives kept apart on purpose.

    A 기준 list read as a document list is visible to a user and wrong in front of them; a missed
    procedure is invisible. One F1 hides which of the two happened.
    """

    label: str
    true_positives: int
    false_positives: int
    false_negatives: int
    false_positive_examples: list[str] = field(default_factory=list)
    false_negative_examples: list[str] = field(default_factory=list)

    @property
    def precision(self) -> float | None:
        denominator = self.true_positives + self.false_positives
        return self.true_positives / denominator if denominator else None

    @property
    def recall(self) -> float | None:
        denominator = self.true_positives + self.false_negatives
        return self.true_positives / denominator if denominator else None


def score_detection(
    *, label: str, marked: Iterable[str], detected: Iterable[str], examples: int = 10
) -> BinaryDetection:
    marked_set, detected_set = set(marked), set(detected)
    false_positives = sorted(detected_set - marked_set)
    false_negatives = sorted(marked_set - detected_set)
    return BinaryDetection(
        label=label,
        true_positives=len(marked_set & detected_set),
        false_positives=len(false_positives),
        false_negatives=len(false_negatives),
        false_positive_examples=false_positives[:examples],
        false_negative_examples=false_negatives[:examples],
    )


# --- pilot -------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Retention:
    cohort: int
    weeks: int
    retained: int
    #: Weekly active counts, oldest week first, so a cohort that decayed reads differently from one
    #: that never started.
    weekly_active: list[int] = field(default_factory=list)

    @property
    def rate(self) -> float | None:
        return self.retained / self.cohort if self.cohort else None


def score_retention(
    *, cohort: Iterable[str], weekly_users: Sequence[Iterable[str]], weeks: int
) -> Retention:
    """Voluntary use at least once a week for ``weeks`` **consecutive** weeks.

    Consecutive is enforced by intersection across every week in the window rather than by counting
    active weeks: a user who used it in weeks 1, 2 and 4 has not met a four-consecutive-week bar,
    and a rate that counted them would report a retention the pilot did not observe.
    """
    cohort_set = set(cohort)
    windows = [set(users) & cohort_set for users in weekly_users[-weeks:]]
    retained = set.intersection(*windows) if len(windows) == weeks and windows else set()
    return Retention(
        cohort=len(cohort_set),
        weeks=weeks,
        retained=len(retained),
        weekly_active=[len(window) for window in windows],
    )


def time_saving(*, baseline_minutes: float, measured_minutes: float) -> float | None:
    """Share of the manual time saved. Negative when the system is slower, and reported as such."""
    if baseline_minutes <= 0:
        return None
    return (baseline_minutes - measured_minutes) / baseline_minutes


__all__ = [
    "AssessedCitation",
    "AxisScore",
    "BinaryDetection",
    "BlindAssessment",
    "DetectionCoverage",
    "DeterminismScore",
    "ExtractionScore",
    "ObservedAnswer",
    "ObservedCitation",
    "PollCoverage",
    "QueryScore",
    "Retention",
    "expected_polls",
    "hallucination_rate",
    "score_assessment",
    "score_detection",
    "score_determinism",
    "score_extraction",
    "score_queries",
    "score_retention",
    "time_saving",
]
