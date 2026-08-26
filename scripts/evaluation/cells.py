"""Which cells the harness measures, and where each one's wrong-cell items come from.

This was ``GATED = {"mfds_samd": "mfds_cosmetic", …}`` in :mod:`.cli` — a dict doing two jobs at
once, which was invisible while there were two cells and each was the other's only neighbour.
phase2.0a takes it to four and the two jobs separate:

- **Which cells are measurable**, and of those, which claim the four per-cell trust gates. Not the
  same question: the FDA cells are measurable and **not gated**, because Phase 1 Go is still
  required before any Phase 2 cell is declared gated (phase2.0a *Deviations* 4).
- **Which cell supplies the "asked in the wrong cell" items.** With two cells this was forced. With
  four it is a decision, and the file records it beside the value rather than only in the plan.

There is **no fallback map in this module**, and that is the point of moving it: a default here
would be the hardcoded dict again, one import away, and it would be what ran the day the file was
mis-mounted — silently measuring a different set of cells than the operator believed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

CONFIG_NAME = "cells.json"


@dataclass(frozen=True, slots=True)
class CellConfig:
    """One cell's place in the harness."""

    slug: str
    #: Whether the four per-cell trust gates are claimed for this cell.
    gated: bool
    #: Cells whose real obligations are asked *here* with cross-cell off, where declining is the
    #: correct answer (ADR-0006 decision 9). More than one is allowed: a cross-domain neighbour and
    #: a cross-authority one are different failure modes.
    neighbours: tuple[str, ...]
    #: Why these neighbours. Carried so the decision is legible where it is made.
    note: str = ""


class ConfigError(RuntimeError):
    """The cell configuration is missing or does not describe a usable harness."""


def load(eval_dir: Path) -> dict[str, CellConfig]:
    """Read ``cells.json`` from the evaluation directory, or fail saying where it looked."""
    path = eval_dir / CONFIG_NAME
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(
            f"no {CONFIG_NAME} at {path}. The harness reads its cell map from the evaluation "
            "directory; set REGOPS_EVAL_DIR, or mount docs/eval at /eval."
        ) from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path} is not valid JSON: {exc}") from exc

    entries = raw.get("cells")
    if not isinstance(entries, dict) or not entries:
        raise ConfigError(f"{path} carries no 'cells' object")

    out: dict[str, CellConfig] = {}
    for slug, value in entries.items():
        if not isinstance(value, dict):
            raise ConfigError(f"{path}: {slug} is not an object")
        neighbours = value.get("neighbours") or []
        if not isinstance(neighbours, list) or not all(isinstance(n, str) for n in neighbours):
            raise ConfigError(f"{path}: {slug}.neighbours must be a list of cell slugs")
        out[slug] = CellConfig(
            slug=slug,
            gated=bool(value.get("gated", False)),
            neighbours=tuple(neighbours),
            note=str(value.get("note") or ""),
        )

    _validate(out, path=path)
    return out


def _validate(config: dict[str, CellConfig], *, path: Path) -> None:
    """Catch the two mistakes that would otherwise show up as a silently wrong score.

    A neighbour that is not a configured cell fails at seed time with a corpus error, which is
    survivable. A cell that is its **own** neighbour does not fail at all: it would generate
    wrong-cell items out of the very cell they are asked in, whose correct answer is then to
    *answer* rather than decline — so the axis would score the opposite of what it measures.
    """
    for cell in config.values():
        if cell.slug in cell.neighbours:
            raise ConfigError(
                f"{path}: {cell.slug} lists itself as a neighbour. Wrong-cell items would be "
                "drawn from the cell they are asked in, where declining is not the right answer."
            )
        for neighbour in cell.neighbours:
            if neighbour not in config:
                raise ConfigError(
                    f"{path}: {cell.slug} names neighbour {neighbour!r}, which is not configured"
                )
        if not cell.neighbours:
            raise ConfigError(
                f"{path}: {cell.slug} has no neighbours, so it can carry no cross-cell axis"
            )


@lru_cache(maxsize=4)
def _cached(eval_dir: str) -> dict[str, CellConfig]:
    return load(Path(eval_dir))


def for_dir(eval_dir: Path) -> dict[str, CellConfig]:
    """:func:`load`, memoised per directory — the CLI reads this on every subcommand."""
    return _cached(str(eval_dir))


def as_json(config: dict[str, CellConfig]) -> dict[str, Any]:
    """The configuration as it is recorded into a run artifact, so a score names its own inputs."""
    return {
        slug: {"gated": cell.gated, "neighbours": list(cell.neighbours)}
        for slug, cell in sorted(config.items())
    }


__all__ = ["CONFIG_NAME", "CellConfig", "ConfigError", "as_json", "for_dir", "load"]
