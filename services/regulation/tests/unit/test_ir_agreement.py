"""The atomicity agreement measurement (``scripts/ir_agreement.py``).

The script exists because ADR-0004 decision 1's rule is worth nothing unless somebody checks that
two readers applying it land in the same place. These tests guard the two ways the measurement could
quietly lie: scoring only the clauses both raters found easy, and reporting a same-rater re-read as
if it were two raters agreeing.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[4] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from ir_agreement import AGREEMENT_FLOOR, Markup, compare, render  # noqa: E402


def _markup(rater: str, counts: dict[str, int], marked: date | None = None) -> Markup:
    return Markup(rater=rater, marked_at=marked, counts=counts)


PERFECT = {"제5조": 3, "제6조": 0, "제7조": 1}


def test_identical_markups_score_perfect_agreement() -> None:
    result = compare(_markup("a", PERFECT), _markup("b", dict(PERFECT)))

    assert result.mode == "inter-rater"
    assert result.exact_agreement == 1.0
    assert result.mean_abs_delta == 0.0
    assert result.disagreements == []
    assert result.passes


def test_disagreements_are_reported_widest_first() -> None:
    result = compare(
        _markup("a", {"제5조": 3, "제6조": 1, "제7조": 1}),
        _markup("b", {"제5조": 1, "제6조": 0, "제7조": 1}),
    )

    assert result.exact_agreement == pytest.approx(1 / 3)
    assert [path for path, _, _ in result.disagreements] == ["제5조", "제6조"]
    assert not result.passes


def test_a_score_below_the_floor_fails() -> None:
    """The floor gates a release; it is not advisory."""
    a = {f"제{n}조": 1 for n in range(10)}
    b = a | {"제0조": 2, "제1조": 2, "제2조": 2}
    assert compare(_markup("a", a), _markup("b", b)).exact_agreement < AGREEMENT_FLOOR
    assert not compare(_markup("a", a), _markup("b", b)).passes


def test_an_explicit_sample_fixes_the_denominator() -> None:
    """Without it, a rater raises their score by skipping the clauses they found hard.

    ``제9조`` is marked by only one rater. Scored over the intersection it disappears; scored over
    the declared sample it is a disagreement, which is the honest reading.
    """
    a = _markup("a", {"제5조": 1, "제9조": 4})
    b = _markup("b", {"제5조": 1})

    intersection = compare(a, b)
    assert intersection.sample_size == 1
    assert intersection.exact_agreement == 1.0
    assert any("dropped" in warning for warning in intersection.warnings)

    declared = compare(a, b, sample=["제5조", "제9조"])
    assert declared.sample_size == 2
    assert declared.exact_agreement == 0.5
    assert any("unmarked by at least one rater" in warning for warning in declared.warnings)


def test_same_rater_twice_is_labelled_test_retest_and_carries_the_caveat() -> None:
    """The mode is never inferred generously.

    Phase 1 staffs one RA, so this is the mode that will actually run — and the number it produces
    cannot detect a rater's consistent private reading of an ambiguous rule. The caveat travels with
    the score so a Go/No-Go report cannot cite one without the other.
    """
    result = compare(
        _markup("kim", PERFECT, date(2026, 8, 1)),
        _markup("kim", dict(PERFECT), date(2026, 9, 1)),
    )

    assert result.mode == "test-retest"
    assert any("TEST-RETEST, NOT INTER-RATER" in warning for warning in result.warnings)
    assert "TEST-RETEST, NOT INTER-RATER" in render(result)


def test_test_retest_under_the_separation_floor_is_flagged() -> None:
    """Two days apart is recall, not re-application of the rule."""
    result = compare(
        _markup("kim", PERFECT, date(2026, 8, 1)),
        _markup("kim", dict(PERFECT), date(2026, 8, 3)),
    )
    assert any("under the 14-day floor" in warning for warning in result.warnings)


def test_markup_without_clauses_is_refused(tmp_path: Path) -> None:
    """ "I did not look at it" must not read as "I judged it to yield nothing"."""
    path = tmp_path / "empty.json"
    path.write_text('{"rater": "a", "clauses": {}}', encoding="utf-8")
    with pytest.raises(SystemExit):
        Markup.load(path)
