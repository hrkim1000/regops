"""The cell map as configuration, and the wrong-cell axis it feeds.

``GATED = {"mfds_samd": "mfds_cosmetic", …}`` was a dict in ``cli.py`` doing two jobs at once —
naming the measurable cells *and* pairing each with its wrong-cell source. Invisible while there
were two cells and each was the other's only option; a decision once there are four.

What is worth testing here is the validation, not the parsing. A malformed file fails loudly on the
next line. A file that parses and is *wrong* does not: it produces a set that scores the opposite of
what the axis measures, and the number looks ordinary.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from evaluation import cells as cells_config
from evaluation.seed import Article, generate_cross_domain

REPO = Path(__file__).resolve().parents[3]


def _write(tmp_path: Path, payload: dict) -> Path:
    (tmp_path / cells_config.CONFIG_NAME).write_text(json.dumps(payload), encoding="utf-8")
    return tmp_path


# --- the shipped file ---------------------------------------------------------------------------


def test_the_shipped_configuration_is_valid() -> None:
    """``docs/eval/cells.json`` is what the harness runs on; a broken one is a broken run."""
    config = cells_config.load(REPO / "docs" / "eval")
    assert set(config) == {"mfds_samd", "mfds_cosmetic", "fda_samd", "fda_cosmetic"}


def test_the_gated_pair_is_the_mfds_pair_and_the_fda_cells_are_not_gated() -> None:
    """`gated` is not "the harness can measure it". Phase 1 Go is still required before any Phase 2
    cell is declared gated (phase2.0a *Deviations* 4), so the FDA cells are measurable and not
    gated — and the file has to keep saying so rather than drifting to whatever ran last."""
    config = cells_config.load(REPO / "docs" / "eval")
    assert {slug for slug, cell in config.items() if cell.gated} == {"mfds_samd", "mfds_cosmetic"}


def test_the_gated_cells_neighbours_did_not_move_when_fda_arrived() -> None:
    """The MFDS golden sets are phase 1.6 gate inputs. Adding two cells must not change what the
    gated pair is measured against as a side effect — the same discipline as *Deviations* 26."""
    config = cells_config.load(REPO / "docs" / "eval")
    assert config["mfds_samd"].neighbours == ("mfds_cosmetic",)
    assert config["mfds_cosmetic"].neighbours == ("mfds_samd",)


def test_each_fda_cell_carries_both_a_cross_domain_and_a_cross_authority_neighbour() -> None:
    """Different failure modes, so choosing one leaves the other unmeasured — and the file records
    which is which in its own `note`, where the decision is made."""
    config = cells_config.load(REPO / "docs" / "eval")
    assert set(config["fda_samd"].neighbours) == {"fda_cosmetic", "mfds_samd"}
    assert set(config["fda_cosmetic"].neighbours) == {"fda_samd", "mfds_cosmetic"}
    assert config["fda_samd"].note


# --- validation ---------------------------------------------------------------------------------


def test_a_missing_file_says_where_it_looked(tmp_path: Path) -> None:
    """There is deliberately no fallback map in the module: a default would be the hardcoded dict
    again, and it would be what ran the day the file was mis-mounted."""
    with pytest.raises(cells_config.ConfigError, match=r"no cells\.json at"):
        cells_config.load(tmp_path)


def test_a_cell_that_is_its_own_neighbour_is_refused(tmp_path: Path) -> None:
    """**The one that would not fail on its own.** Wrong-cell items drawn from the cell they are
    asked in have `needs verification` as their expected outcome — but answering them is correct
    there, so every one would score as a failure and the axis would report the opposite of what it
    measures."""
    root = _write(tmp_path, {"cells": {"a": {"neighbours": ["a"]}}})
    with pytest.raises(cells_config.ConfigError, match="lists itself as a neighbour"):
        cells_config.load(root)


def test_a_neighbour_that_is_not_configured_is_refused(tmp_path: Path) -> None:
    root = _write(tmp_path, {"cells": {"a": {"neighbours": ["ghost"]}}})
    with pytest.raises(cells_config.ConfigError, match="not configured"):
        cells_config.load(root)


def test_a_cell_with_no_neighbour_can_carry_no_cross_cell_axis(tmp_path: Path) -> None:
    root = _write(tmp_path, {"cells": {"a": {"neighbours": []}}})
    with pytest.raises(cells_config.ConfigError, match="no neighbours"):
        cells_config.load(root)


def test_an_empty_cells_object_is_refused(tmp_path: Path) -> None:
    root = _write(tmp_path, {"cells": {}})
    with pytest.raises(cells_config.ConfigError, match="no 'cells' object"):
        cells_config.load(root)


# --- the axis the configuration feeds -----------------------------------------------------------


def _articles(prefix: str, count: int) -> list[Article]:
    return [
        Article(
            document=f"{prefix} 규정",
            version_id="v",
            clause_path=f"제{n}조",
            article=f"제{n}조",
            heading=f"{prefix} 표제 {n}",
            ordinal=n,
        )
        for n in range(1, count + 1)
    ]


def test_one_neighbour_fills_the_axis_exactly_as_it_always_did() -> None:
    """The regression pin for the gated pair: a single neighbour must produce the same 30 items it
    produced when the neighbour was a scalar, or the MFDS sets move underneath their own gate."""
    items = generate_cross_domain("cos", [("mfds_samd", _articles("의료기기", 60))])
    assert len(items) == 30
    assert [item.id for item in items][:3] == ["cos-cross-001", "cos-cross-002", "cos-cross-003"]
    assert all("Belongs to mfds_samd" in (item.notes or "") for item in items)


def test_two_neighbours_split_the_budget_and_the_axis_keeps_its_denominator() -> None:
    """A per-axis score should not rest on a handful, which is why the targets exist at all — so
    adding a second neighbour divides the axis rather than doubling or halving it."""
    items = generate_cross_domain(
        "samd",
        [("fda_cosmetic", _articles("화장품", 40)), ("mfds_samd", _articles("의료기기", 40))],
    )
    assert len(items) == 30
    by_source = {
        slug: sum(1 for item in items if f"Belongs to {slug}" in (item.notes or ""))
        for slug in ("fda_cosmetic", "mfds_samd")
    }
    assert by_source == {"fda_cosmetic": 15, "mfds_samd": 15}
    # Ids stay a single unbroken run, so an item is addressable without knowing which neighbour it
    # came from.
    assert [item.id for item in items] == [f"samd-cross-{n:03d}" for n in range(1, 31)]


def test_an_odd_split_still_fills_the_axis() -> None:
    """Three neighbours into 30 is exact; the remainder path is what an uneven target would hit, and
    a short axis is a weaker denominator rather than an error."""
    items = generate_cross_domain(
        "samd",
        [
            ("a", _articles("A", 20)),
            ("b", _articles("B", 20)),
            ("c", _articles("C", 20)),
            ("d", _articles("D", 20)),
        ],
    )
    assert len(items) == 30


def test_a_neighbour_with_no_usable_article_is_skipped_not_counted() -> None:
    """A 삭제 clause has no content to ask about. A neighbour made entirely of them must not consume
    its share of the budget and leave the axis short."""
    deleted = [
        Article(
            document="d",
            version_id="v",
            clause_path=f"제{n}조",
            article=f"제{n}조",
            heading="삭제",
            ordinal=n,
        )
        for n in range(1, 20)
    ]
    items = generate_cross_domain("cos", [("empty", deleted), ("real", _articles("실제", 60))])
    assert len(items) == 30
    assert all("Belongs to real" in (item.notes or "") for item in items)
