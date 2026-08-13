"""Golden-set composition and the report's verdict logic.

Both are places where a permissive default would change a decision rather than a number: a set that
validates without axis coverage lets a citation-accuracy score rest on identifier lookups, and an
unmeasured gate coerced to a pass or a failure moves the Go/No-Go recommendation.
"""

from __future__ import annotations

from datetime import date

from evaluation.goldenset import GoldenItem, GoldenSet, validate_composition
from evaluation.report import GATES_BY_KEY, GateResult, GoNoGoReport, render

from regops_shared.constants import (
    GOLDEN_SET_MIN_ITEMS_PER_AXIS,
    Domain,
    EvaluationAxis,
    ExpectedOutcome,
)


def _full_set(**overrides) -> GoldenSet:
    """A set that satisfies every axis floor, so a test can break exactly one thing."""
    items: list[GoldenItem] = []
    for axis in EvaluationAxis:
        refuses = axis in {
            EvaluationAxis.MIS_CITATION,
            EvaluationAxis.CROSS_DOMAIN,
            EvaluationAxis.UNANSWERABLE,
        }
        for index in range(GOLDEN_SET_MIN_ITEMS_PER_AXIS):
            items.append(
                GoldenItem(
                    id=f"{axis.value}-{index}",
                    axis=axis,
                    question="?",
                    expected_outcome=(
                        ExpectedOutcome.NEEDS_VERIFICATION if refuses else ExpectedOutcome.ANSWERED
                    ),
                    expected_clause_paths=() if refuses else ("제1조",),
                    forbidden_clause_paths=(
                        ("제99조",) if axis is EvaluationAxis.MIS_CITATION else ()
                    ),
                )
            )
    payload = {
        "cell": "mfds_cosmetic",
        "domain": Domain.COSMETIC,
        "set_version": "1.0.0",
        "items": tuple(items),
        **overrides,
    }
    return GoldenSet(**payload)


def test_a_complete_set_is_structurally_valid_but_not_citable_until_signed():
    composition = validate_composition(_full_set())
    assert composition.structurally_valid
    assert not composition.citable
    assert any("NOT RA-SIGNED-OFF" in warning for warning in composition.warnings)


def test_sign_off_is_what_makes_a_set_citable():
    composition = validate_composition(
        _full_set(ra_signed_off=True, signed_off_by="ra", signed_off_at=date(2026, 8, 13))
    )
    assert composition.citable


def test_an_axis_below_the_floor_fails_validation():
    """A set of only identifier lookups measures the easy half and scores well doing it."""
    complete = _full_set()
    thin = GoldenSet(
        cell=complete.cell,
        domain=complete.domain,
        set_version=complete.set_version,
        items=tuple(item for item in complete.items if item.axis is not EvaluationAxis.CONCEPTUAL),
    )
    composition = validate_composition(thin)
    assert not composition.structurally_valid
    assert any("conceptual" in error for error in composition.errors)


def test_an_axis_that_asserts_a_refusal_cannot_expect_an_answer():
    item = GoldenItem(
        id="x",
        axis=EvaluationAxis.CROSS_DOMAIN,
        question="?",
        expected_outcome=ExpectedOutcome.ANSWERED,
        expected_clause_paths=("제1조",),
    )
    composition = validate_composition(_with(item))
    assert any("asserts a refusal" in error for error in composition.errors)


def test_a_mis_citation_item_without_a_forbidden_path_is_just_an_unanswerable_one():
    item = GoldenItem(
        id="x",
        axis=EvaluationAxis.MIS_CITATION,
        question="?",
        expected_outcome=ExpectedOutcome.NEEDS_VERIFICATION,
    )
    composition = validate_composition(_with(item))
    assert any("mis-citation trap" in error for error in composition.errors)


def test_cross_cell_defeats_a_cross_domain_item():
    item = GoldenItem(
        id="x",
        axis=EvaluationAxis.CROSS_DOMAIN,
        question="?",
        expected_outcome=ExpectedOutcome.NEEDS_VERIFICATION,
        cross_cell=True,
    )
    composition = validate_composition(_with(item))
    assert any("cross_cell=true defeats" in error for error in composition.errors)


def test_an_answerable_item_with_no_expected_clause_has_nothing_to_score():
    item = GoldenItem(
        id="x",
        axis=EvaluationAxis.IDENTIFIER,
        question="?",
        expected_outcome=ExpectedOutcome.ANSWERED,
    )
    composition = validate_composition(_with(item))
    assert any("no expected_clause_paths" in error for error in composition.errors)


def test_duplicate_ids_are_caught():
    complete = _full_set()
    duplicated = GoldenSet(
        cell=complete.cell,
        domain=complete.domain,
        set_version=complete.set_version,
        items=(*complete.items, complete.items[0]),
    )
    assert any("duplicate id" in error for error in validate_composition(duplicated).errors)


def _with(extra: GoldenItem) -> GoldenSet:
    complete = _full_set()
    return GoldenSet(
        cell=complete.cell,
        domain=complete.domain,
        set_version=complete.set_version,
        items=(*complete.items, extra),
    )


# --- the report's verdict ------------------------------------------------------------------------


def _result(key: str, value: float | None, cell: str = "mfds_samd") -> GateResult:
    return GateResult(
        gate=GATES_BY_KEY[key],
        cell=cell,
        value=value,
        evidence="test",
        unmeasured_reason=None if value is not None else "not measured",
    )


def test_a_ceiling_gate_passes_below_its_threshold_and_a_floor_gate_above_it():
    assert _result("hallucination_rate", 0.01).passed is True
    assert _result("hallucination_rate", 0.05).passed is False
    assert _result("citation_accuracy", 0.95).passed is True
    assert _result("citation_accuracy", 0.85).passed is False


def test_an_unmeasured_gate_is_neither_a_pass_nor_a_failure():
    result = _result("citation_accuracy", None)
    assert result.passed is None
    assert result.verdict == "미측정"
    assert result.render_value() == "—"


def test_any_unmeasured_gate_makes_the_recommendation_incomplete():
    """A report that guessed either way would be making the decision rather than informing it."""
    built = GoNoGoReport(
        generated_at=date(2026, 8, 13),
        regime={},
        results=[_result("citation_accuracy", 0.95), _result("hallucination_rate", None)],
    )
    assert built.recommendation == "INCOMPLETE"


def test_four_shortfalls_in_one_cell_calls_no_go_even_when_the_other_cell_is_clean():
    """A cell that misses is not offset by the other passing."""
    failing = [
        _result("detection_coverage", 0.5),
        _result("detection_latency", 99.0),
        _result("citation_accuracy", 0.5),
        _result("hallucination_rate", 0.5),
    ]
    passing = [
        _result("detection_coverage", 1.0, cell="mfds_cosmetic"),
        _result("citation_accuracy", 1.0, cell="mfds_cosmetic"),
    ]
    built = GoNoGoReport(generated_at=date(2026, 8, 13), regime={}, results=[*failing, *passing])
    assert built.recommendation == "NO-GO"


def test_shortfalls_are_not_pooled_across_cells():
    """Six failures overall, three in each cell and four in neither. Pooling them would call
    No-Go on a run the rule does not — the rule is per cell."""
    results = [
        *(_result(key, 0.0) for key in ("detection_coverage", "citation_accuracy")),
        _result("hallucination_rate", 0.9),
        *(
            _result(key, 0.0, cell="mfds_cosmetic")
            for key in ("detection_coverage", "citation_accuracy")
        ),
        _result("hallucination_rate", 0.9, cell="mfds_cosmetic"),
    ]
    built = GoNoGoReport(generated_at=date(2026, 8, 13), regime={}, results=results)
    assert built.recommendation == "GO"


def test_an_unscoped_gate_counts_against_every_cell():
    """Pilot retention and research-time savings are measured over the pilot as a whole. Matching
    shortfalls by slug alone would mean a failed retention gate could never call No-Go."""
    results = [
        *(_result(key, 0.0) for key in ("detection_coverage", "citation_accuracy")),
        _result("hallucination_rate", 0.9),
        _result("pilot_retention", 0.1, cell=GoNoGoReport.UNSCOPED),
    ]
    built = GoNoGoReport(generated_at=date(2026, 8, 13), regime={}, results=results)
    assert built.cells == ["mfds_samd"]
    assert built.recommendation == "NO-GO"


def test_the_rendered_report_says_a_gate_was_not_measured_rather_than_leaving_a_blank():
    built = GoNoGoReport(
        generated_at=date(2026, 8, 13),
        regime={"llm_model": "gemma3:4b"},
        results=[_result("citation_accuracy", None)],
    )
    rendered = render(built)
    assert "미측정" in rendered
    assert "## Not measured" in rendered
    assert "not measured" in rendered
