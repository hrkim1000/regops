"""The scoring math, against inputs whose right answer was worked out by hand.

A bug here produces a *passing* gate, and a passing gate is not investigated. These cases are
therefore written against the failure modes the design is meant to prevent, not against the
implementation: a harness error must not read as a refusal, a refusal must not read as an answer,
an unmeasured gate must not read as a zero, and three weeks of use must not read as four.
"""

from __future__ import annotations

import pytest
from evaluation.goldenset import GoldenItem, article_of
from evaluation.score import (
    AssessedCitation,
    ObservedAnswer,
    ObservedCitation,
    expected_polls,
    hallucination_rate,
    score_assessment,
    score_detection,
    score_determinism,
    score_extraction,
    score_queries,
    score_retention,
    time_saving,
)

from regops_shared.constants import EvaluationAxis, ExpectedOutcome


def _item(
    item_id: str,
    axis: EvaluationAxis,
    outcome: ExpectedOutcome,
    *,
    expected: tuple[str, ...] = (),
    forbidden: tuple[str, ...] = (),
) -> GoldenItem:
    return GoldenItem(
        id=item_id,
        axis=axis,
        question="?",
        expected_outcome=outcome,
        expected_clause_paths=expected,
        forbidden_clause_paths=forbidden,
    )


def _answered(
    item_id: str, *citations: ObservedCitation, scope: str | None = None
) -> ObservedAnswer:
    return ObservedAnswer(
        item_id=item_id, status="answered", citations=citations, effective_date_scope=scope
    )


# --- article matching ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("제2장/제5조", "제5조"),
        ("제3장/제1절/제8조/제2항", "제8조"),
        ("제5조", "제5조"),
        ("제2장/제3조의2", "제3조의2"),
        ("별표1/표1/행1", "행1"),
    ],
)
def test_article_of_reduces_to_the_unit_an_expectation_is_recorded_at(path: str, expected: str):
    assert article_of(path) == expected


def test_citation_to_a_sub_clause_matches_an_expectation_recorded_at_the_article():
    """제5조제2항 supports an expectation of 제5조. Demanding exact equality would score a
    correct citation as a miss — and the corpus nests some 조 under 절 and some not."""
    items = [
        _item("a", EvaluationAxis.IDENTIFIER, ExpectedOutcome.ANSWERED, expected=("제2장/제5조",))
    ]
    observed = {"a": _answered("a", ObservedCitation("v1", "제2장/제5조/제2항", resolves=True))}
    result = score_queries("cell", items, observed)
    assert result.overall.citations_expected == 1


# --- outcome scoring -----------------------------------------------------------------------------


def test_a_harness_error_is_not_a_refusal():
    """The failure this separation exists to prevent: a question the harness never got an answer
    to, counted as the product declining, moves the refusal rate the healthy-looking way."""
    items = [_item("a", EvaluationAxis.UNANSWERABLE, ExpectedOutcome.NEEDS_VERIFICATION)]
    observed = {"a": ObservedAnswer(item_id="a", status="error", error="timeout")}
    result = score_queries("cell", items, observed)

    assert result.harness_errors == 1
    assert result.scored_items == 0
    assert result.overall.refusals == 0
    assert result.overall.outcome_accuracy is None
    assert result.refusal_rate is None


def test_an_item_that_was_never_asked_is_neither_an_error_nor_a_pass():
    """A bounded run leaves most of the set unasked. Counting those as harness errors would report
    a broken harness on every sample; counting them as scored would put them in a denominator they
    were never part of."""
    items = [_item("a", EvaluationAxis.IDENTIFIER, ExpectedOutcome.ANSWERED, expected=("제1조",))]
    result = score_queries("cell", items, {})

    assert result.not_attempted == 1
    assert result.harness_errors == 0
    assert result.scored_items == 0
    assert result.overall.outcome_correct == 0
    assert result.overall.outcome_accuracy is None


def test_unasked_items_do_not_dilute_the_rates_of_the_ones_that_ran():
    """The bug this replaced: a 2-item sample of a 162-item set reported 160 harness errors and
    divided its accuracy by the whole set."""
    items = [
        _item(f"a{index}", EvaluationAxis.IDENTIFIER, ExpectedOutcome.ANSWERED, expected=("제1조",))
        for index in range(10)
    ]
    observed = {"a0": _answered("a0", ObservedCitation("v1", "제1조", resolves=True))}
    result = score_queries("cell", items, observed)

    assert result.not_attempted == 9
    assert result.scored_items == 1
    assert result.overall.outcome_accuracy == 1.0
    assert result.answer_rate == 1.0


def test_needs_review_counts_as_a_refusal():
    """Sub-threshold confidence does not reach the reader as final, so crediting it as an answer
    would credit the system with an answer nobody was given."""
    items = [_item("a", EvaluationAxis.UNANSWERABLE, ExpectedOutcome.NEEDS_VERIFICATION)]
    observed = {"a": ObservedAnswer(item_id="a", status="needs_review")}
    result = score_queries("cell", items, observed)
    assert result.overall.refusals == 1
    assert result.overall.outcome_correct == 1


def test_refusing_a_question_that_should_have_been_answered_is_a_miss():
    items = [_item("a", EvaluationAxis.IDENTIFIER, ExpectedOutcome.ANSWERED, expected=("제1조",))]
    observed = {"a": ObservedAnswer(item_id="a", status="needs_verification")}
    result = score_queries("cell", items, observed)
    assert result.overall.outcome_correct == 0
    assert result.misses == ["a"]


def test_answering_a_cross_domain_question_is_a_miss():
    items = [_item("a", EvaluationAxis.CROSS_DOMAIN, ExpectedOutcome.NEEDS_VERIFICATION)]
    observed = {"a": _answered("a", ObservedCitation("v1", "제1조", resolves=True))}
    result = score_queries("cell", items, observed)
    assert result.overall.outcome_correct == 0
    assert result.per_axis[EvaluationAxis.CROSS_DOMAIN].outcome_accuracy == 0.0


# --- hallucination -------------------------------------------------------------------------------


def test_a_citation_that_resolves_to_nothing_makes_its_answer_hallucinating():
    items = [_item("a", EvaluationAxis.IDENTIFIER, ExpectedOutcome.ANSWERED, expected=("제1조",))]
    observed = {
        "a": _answered(
            "a",
            ObservedCitation("v1", "제1조", resolves=True),
            ObservedCitation("v1", "제99조", resolves=False),
        )
    }
    result = score_queries("cell", items, observed)
    assert result.overall.hallucinating_answers == 1
    assert result.overall.citations_resolving == 1
    assert result.overall.hallucination_nonexistent == 1.0


def test_an_answer_is_counted_once_however_many_of_its_citations_are_bad():
    items = [_item("a", EvaluationAxis.IDENTIFIER, ExpectedOutcome.ANSWERED, expected=("제1조",))]
    observed = {
        "a": _answered(
            "a",
            ObservedCitation("v1", "제98조", resolves=False),
            ObservedCitation("v1", "제99조", resolves=False),
        )
    }
    assert score_queries("cell", items, observed).overall.hallucinating_answers == 1


def test_citing_a_forbidden_path_is_a_hallucination_even_when_the_clause_resolves():
    """The trap the mechanical check cannot catch alone. Asked what a deleted 제21조 requires, an
    answer citing 제20조 resolves perfectly well and is still the wrong clause."""
    items = [
        _item(
            "a",
            EvaluationAxis.MIS_CITATION,
            ExpectedOutcome.NEEDS_VERIFICATION,
            forbidden=("제4장/제20조",),
        )
    ]
    observed = {"a": _answered("a", ObservedCitation("v1", "제4장/제20조", resolves=True))}
    result = score_queries("cell", items, observed)
    assert result.overall.trap_citations == 1
    assert result.overall.hallucinating_answers == 1


def test_a_refusal_that_names_a_forbidden_path_is_not_counted_as_a_hallucinating_answer():
    """No answer reached a reader, so there is no output to have hallucinated in."""
    items = [
        _item(
            "a",
            EvaluationAxis.MIS_CITATION,
            ExpectedOutcome.NEEDS_VERIFICATION,
            forbidden=("제99조",),
        )
    ]
    observed = {
        "a": ObservedAnswer(
            item_id="a",
            status="needs_verification",
            citations=(ObservedCitation("v1", "제99조", resolves=False),),
        )
    }
    result = score_queries("cell", items, observed)
    assert result.overall.trap_citations == 1
    assert result.overall.hallucinating_answers == 0


def test_hallucination_rate_never_exceeds_one():
    """Summing the two halves could put the rate above 100% — a number that would quietly
    discredit the whole report."""
    assert hallucination_rate(
        answers=10, fabricated_citation_answers=7, contradicting_answers=6
    ) == pytest.approx(0.7)
    assert (
        hallucination_rate(answers=0, fabricated_citation_answers=0, contradicting_answers=0)
        is None
    )


# --- effective-date scope ------------------------------------------------------------------------


def test_an_answer_stating_no_effective_date_is_visible_in_the_scope_rate():
    items = [
        _item("a", EvaluationAxis.EFFECTIVE_DATE, ExpectedOutcome.ANSWERED, expected=("제1조",)),
        _item("b", EvaluationAxis.EFFECTIVE_DATE, ExpectedOutcome.ANSWERED, expected=("제1조",)),
    ]
    observed = {
        "a": _answered("a", ObservedCitation("v1", "제1조", resolves=True), scope="2026-04-02"),
        "b": _answered("b", ObservedCitation("v1", "제1조", resolves=True)),
    }
    result = score_queries("cell", items, observed)
    assert result.per_axis[EvaluationAxis.EFFECTIVE_DATE].scope_statement_rate == 0.5


# --- blind assessment ----------------------------------------------------------------------------


def test_citation_accuracy_is_per_citation_and_contradiction_is_per_answer():
    rows = [
        AssessedCitation("a", 0, "제1조", supports=True),
        AssessedCitation("a", 1, "제2조", supports=False, contradicts=True),
        AssessedCitation("b", 0, "제3조", supports=True),
    ]
    assessment = score_assessment(rows)
    assert assessment.citation_accuracy == pytest.approx(2 / 3)
    assert assessment.answers_assessed == 2
    assert assessment.answers_contradicting == 1
    assert assessment.contradiction_rate == 0.5


# --- extraction ----------------------------------------------------------------------------------


def test_extraction_scores_over_the_fixed_sample_not_the_intersection():
    """The denominator is fixed before either side runs. Scoring over the intersection would let a
    clause the RA skipped count as agreement."""
    result = score_extraction(
        sample=["제1조", "제2조", "제3조"],
        marked={"제1조": 2, "제2조": 1, "제3조": 0},
        extracted={"제1조": 2, "제3조": 1},
    )
    assert result.marked_irs == 3
    assert result.extracted_irs == 3
    assert result.matched_irs == 2
    assert result.clause_level_recall == pytest.approx(2 / 3)
    assert result.clause_level_precision == pytest.approx(2 / 3)
    assert result.missed_clauses == ["제2조"]
    assert result.invented_clauses == ["제3조"]


def test_a_clause_absent_from_both_sides_still_counts_in_the_denominator():
    result = score_extraction(
        sample=["제1조", "제9조"], marked={"제1조": 1}, extracted={"제1조": 1}
    )
    assert result.sample_clauses == 2
    assert result.clause_level_recall == 1.0


def test_determinism_reports_drift_rather_than_asserting_zero():
    result = score_determinism(
        triple="1.2.0/1.2.0/gemma3:4b@0.0",
        first={"제1조": 2, "제2조": 1},
        second={"제1조": 2, "제2조": 2},
    )
    assert result.clauses == 2
    assert result.drifted_clauses == 1
    assert result.drift_rate == 0.5
    assert (result.first_total, result.second_total) == (3, 4)


def test_a_clause_extracted_only_on_the_second_pass_is_drift():
    result = score_determinism(triple="t", first={"제1조": 1}, second={"제1조": 1, "제2조": 1})
    assert result.drifted_clauses == 1


# --- detection -----------------------------------------------------------------------------------


def test_false_positives_and_false_negatives_are_kept_apart():
    """One F1 hides which of the two happened, and only one of them is visible to a user."""
    result = score_detection(
        label="화장품법 시행규칙", marked=["제3조", "제4조", "제5조"], detected=["제3조", "제9조"]
    )
    assert result.true_positives == 1
    assert result.false_positives == 1
    assert result.false_negatives == 2
    assert result.precision == 0.5
    assert result.recall == pytest.approx(1 / 3)
    assert result.false_positive_examples == ["제9조"]


def test_detecting_nothing_gives_undefined_precision_not_zero():
    result = score_detection(label="x", marked=["제1조"], detected=[])
    assert result.precision is None
    assert result.recall == 0.0


# --- polls ---------------------------------------------------------------------------------------


def test_expected_polls_floors_a_partial_interval():
    day = 86400.0
    assert expected_polls(window_seconds=day, interval_seconds=21600) == 4
    assert expected_polls(window_seconds=day, interval_seconds=50000) == 1
    assert expected_polls(window_seconds=day, interval_seconds=0) == 0


# --- retention -----------------------------------------------------------------------------------


def test_retention_requires_consecutive_weeks():
    """A user active in weeks 1, 2 and 4 has not met a four-consecutive-week bar, and a rate that
    counted them would report a retention the pilot did not observe."""
    result = score_retention(
        cohort=["u1", "u2"],
        weekly_users=[{"u1", "u2"}, {"u1", "u2"}, {"u2"}, {"u1", "u2"}],
        weeks=4,
    )
    assert result.retained == 1
    assert result.rate == 0.5
    assert result.weekly_active == [2, 2, 1, 2]


def test_retention_ignores_use_by_people_outside_the_cohort():
    result = score_retention(cohort=["u1"], weekly_users=[{"u1", "stranger"}, {"u1"}], weeks=2)
    assert result.retained == 1
    assert result.weekly_active == [1, 1]


def test_retention_over_an_empty_cohort_is_undefined_not_zero():
    result = score_retention(cohort=[], weekly_users=[set(), set()], weeks=2)
    assert result.rate is None


def test_retention_with_fewer_weeks_of_data_than_the_window_retains_nobody():
    result = score_retention(cohort=["u1"], weekly_users=[{"u1"}], weeks=4)
    assert result.retained == 0


# --- time saving ---------------------------------------------------------------------------------


def test_time_saving_reports_a_slowdown_as_negative():
    assert time_saving(baseline_minutes=60, measured_minutes=30) == 0.5
    assert time_saving(baseline_minutes=30, measured_minutes=45) == pytest.approx(-0.5)
    assert time_saving(baseline_minutes=0, measured_minutes=10) is None
