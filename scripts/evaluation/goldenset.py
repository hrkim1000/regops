"""The golden query set: its shape, its composition rules, and what makes it citable as evidence.

Two properties are enforced here rather than left to whoever runs the harness.

**Composition.** A set of only identifier lookups measures the easy half and scores well doing it,
so coverage is asserted per axis per domain against
:data:`~regops_shared.constants.GOLDEN_SET_MIN_ITEMS_PER_AXIS`. ADR-0006 open question 4 names four
axes; the closed inventory in :class:`~regops_shared.constants.EvaluationAxis` adds cross-domain
(decision 9) and known-unanswerable, because refusing is a correct outcome that has to be scored as
one rather than counted as a failure.

**Provenance.** ``ra_signed_off`` gates whether a scored run may be cited against a gate. A set the
system's own authors wrote and scored themselves is not evidence, however good the questions are —
so the flag exists, it defaults false, and :func:`load` records who signed rather than letting the
harness assume anybody did. Seeding is allowed to *propose* items; only an RA can make them count.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from regops_shared.constants import (
    GOLDEN_SET_MIN_ITEMS_PER_AXIS,
    Domain,
    EvaluationAxis,
    ExpectedOutcome,
)

SCHEMA_VERSION = "1.0"

#: Which axes assert a refusal. Kept as data rather than as a branch in the scorer: "the correct
#: answer is 확인 필요" is a property of the question shape, and reading it off the axis stops an
#: item being authored with an outcome its axis contradicts.
REFUSAL_AXES: frozenset[EvaluationAxis] = frozenset(
    {
        EvaluationAxis.MIS_CITATION,
        EvaluationAxis.CROSS_DOMAIN,
        EvaluationAxis.UNANSWERABLE,
    }
)


@dataclass(frozen=True, slots=True)
class GoldenItem:
    """One question, with what the RA says the system should do with it."""

    id: str
    axis: EvaluationAxis
    question: str
    expected_outcome: ExpectedOutcome
    #: Instrument title, resolved by the validator against the cell's own corpus. A golden item
    #: naming a document that is not in the cell is an authoring error, not a system failure.
    expected_document: str | None = None
    #: Clause paths that support the expected answer. Matching is on the 조 component
    #: (:func:`article_of`), because a citation to 제5조제2항 supports an expectation of 제5조 and
    #: the corpus nests some 조 under 절 and some not.
    expected_clause_paths: tuple[str, ...] = ()
    #: Paths the answer must **not** cite. For a mis-citation trap this is the whole point: the
    #: validator proves the path does not resolve, so citing it is a fabrication and not a
    #: disagreement about relevance.
    forbidden_clause_paths: tuple[str, ...] = ()
    #: Whether the ask sets the explicit cross-cell mode. False on a cross-domain item by design —
    #: the item exists to check that the default bound holds (ADR-0006 decision 9).
    cross_cell: bool = False
    expected_answer: str | None = None
    #: ``seed-generated`` (templated from the clause store) or ``seed-manual`` (written by hand).
    #: An RA reviewing 200 items needs to know which were written by a template.
    authored_by: str = "seed-generated"
    notes: str | None = None

    @property
    def expects_refusal(self) -> bool:
        return self.expected_outcome is ExpectedOutcome.NEEDS_VERIFICATION

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> GoldenItem:
        return cls(
            id=str(payload["id"]),
            axis=EvaluationAxis(payload["axis"]),
            question=str(payload["question"]),
            expected_outcome=ExpectedOutcome(payload["expected_outcome"]),
            expected_document=payload.get("expected_document"),
            expected_clause_paths=tuple(payload.get("expected_clause_paths") or ()),
            forbidden_clause_paths=tuple(payload.get("forbidden_clause_paths") or ()),
            cross_cell=bool(payload.get("cross_cell", False)),
            expected_answer=payload.get("expected_answer"),
            authored_by=str(payload.get("authored_by") or "seed-generated"),
            notes=payload.get("notes"),
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "axis": self.axis.value,
            "question": self.question,
            "expected_outcome": self.expected_outcome.value,
            "expected_document": self.expected_document,
            "expected_clause_paths": list(self.expected_clause_paths),
            "forbidden_clause_paths": list(self.forbidden_clause_paths),
            "cross_cell": self.cross_cell,
            "expected_answer": self.expected_answer,
            "authored_by": self.authored_by,
            "notes": self.notes,
        }


@dataclass(frozen=True, slots=True)
class GoldenSet:
    """One cell's set. Scored separately from every other — a shared score hides one domain
    failing behind the other passing."""

    cell: str
    domain: Domain
    set_version: str
    items: tuple[GoldenItem, ...]
    authored_at: date | None = None
    ra_signed_off: bool = False
    signed_off_by: str | None = None
    signed_off_at: date | None = None
    notes: str | None = None

    @property
    def axis_counts(self) -> dict[EvaluationAxis, int]:
        counter = Counter(item.axis for item in self.items)
        return {axis: counter.get(axis, 0) for axis in EvaluationAxis}

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> GoldenSet:
        if str(payload.get("schema_version")) != SCHEMA_VERSION:
            raise ValueError(
                f"golden set schema_version {payload.get('schema_version')!r}, "
                f"expected {SCHEMA_VERSION!r}"
            )
        return cls(
            cell=str(payload["cell"]),
            domain=Domain(payload["domain"]),
            set_version=str(payload["set_version"]),
            items=tuple(GoldenItem.from_json(row) for row in payload["items"]),
            authored_at=_as_date(payload.get("authored_at")),
            ra_signed_off=bool(payload.get("ra_signed_off", False)),
            signed_off_by=payload.get("signed_off_by"),
            signed_off_at=_as_date(payload.get("signed_off_at")),
            notes=payload.get("notes"),
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "cell": self.cell,
            "domain": self.domain.value,
            "set_version": self.set_version,
            "authored_at": self.authored_at.isoformat() if self.authored_at else None,
            "ra_signed_off": self.ra_signed_off,
            "signed_off_by": self.signed_off_by,
            "signed_off_at": self.signed_off_at.isoformat() if self.signed_off_at else None,
            "notes": self.notes,
            "items": [item.to_json() for item in self.items],
        }


@dataclass(frozen=True, slots=True)
class Composition:
    """The verdict on whether a set is fit to score against, and why."""

    cell: str
    total: int
    axis_counts: dict[EvaluationAxis, int]
    ra_signed_off: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def structurally_valid(self) -> bool:
        return not self.errors

    @property
    def citable(self) -> bool:
        """Whether a run over this set may be quoted against a Go/No-Go gate."""
        return self.structurally_valid and self.ra_signed_off


def validate_composition(golden: GoldenSet) -> Composition:
    """Structure, axis coverage and internal consistency. No database, no network.

    Sign-off is reported rather than enforced here: a set can be structurally perfect and still not
    be evidence, and conflating the two would let "the JSON parses" stand in for "an RA agreed
    these are the right questions."
    """
    errors: list[str] = []
    warnings: list[str] = []

    seen: set[str] = set()
    for item in golden.items:
        if item.id in seen:
            errors.append(f"{item.id}: duplicate id")
        seen.add(item.id)

        expects_refusal_by_axis = item.axis in REFUSAL_AXES
        if expects_refusal_by_axis and not item.expects_refusal:
            errors.append(
                f"{item.id}: axis {item.axis.value} asserts a refusal, but expected_outcome is "
                f"{item.expected_outcome.value}"
            )
        if not expects_refusal_by_axis and item.expects_refusal:
            errors.append(
                f"{item.id}: axis {item.axis.value} expects an answer, but expected_outcome is "
                f"{item.expected_outcome.value}"
            )

        if item.expected_outcome is ExpectedOutcome.ANSWERED and not item.expected_clause_paths:
            errors.append(
                f"{item.id}: expects an answer with no expected_clause_paths — nothing to score "
                f"citation accuracy against"
            )
        if item.axis is EvaluationAxis.MIS_CITATION and not item.forbidden_clause_paths:
            errors.append(
                f"{item.id}: a mis-citation trap with no forbidden_clause_paths is an ordinary "
                f"unanswerable question"
            )
        if item.axis is EvaluationAxis.CROSS_DOMAIN and item.cross_cell:
            errors.append(
                f"{item.id}: cross_cell=true defeats the item — it exists to check that the "
                f"default cell bound holds (ADR-0006 decision 9)"
            )
        overlap = set(item.expected_clause_paths) & set(item.forbidden_clause_paths)
        if overlap:
            errors.append(f"{item.id}: {sorted(overlap)} is both expected and forbidden")

    counts = golden.axis_counts
    for axis, count in counts.items():
        if count < GOLDEN_SET_MIN_ITEMS_PER_AXIS:
            errors.append(
                f"axis {axis.value}: {count} items, below the floor of "
                f"{GOLDEN_SET_MIN_ITEMS_PER_AXIS} — a score on this axis would rest on a handful "
                f"of items"
            )

    manual = sum(1 for item in golden.items if item.authored_by.endswith("manual"))
    if manual and manual < len(golden.items):
        warnings.append(
            f"{len(golden.items) - manual} of {len(golden.items)} items are template-generated; "
            f"review those first — a template cannot write a genuine paraphrase"
        )
    if not golden.ra_signed_off:
        warnings.append(
            "NOT RA-SIGNED-OFF: a run over this set measures the harness, not the product. "
            "It must not be quoted against a Go/No-Go gate until an RA sets ra_signed_off"
        )

    return Composition(
        cell=golden.cell,
        total=len(golden.items),
        axis_counts=counts,
        ra_signed_off=golden.ra_signed_off,
        errors=errors,
        warnings=warnings,
    )


def article_of(clause_path: str) -> str:
    """The 조 component of a path, which is the unit an expectation is recorded at.

    ``제3장/제1절/제8조/제2항`` → ``제8조``. Two reasons this is not string equality. The corpus
    nests some 조 under 절 and some directly under 장, so the same article has different full paths
    in different instruments; and a citation to 제5조제2항 supports an expectation recorded at
    제5조, while demanding an exact match would score a *correct* citation as a miss.

    A path with no 조 segment (an annex row, say) returns its last segment, so exact-match lookups
    are still comparable.
    """
    segments = [segment for segment in clause_path.split("/") if segment]
    if not segments:
        return clause_path
    for segment in segments:
        if segment.endswith("조") or "조의" in segment:
            return segment
    return segments[-1]


def load(path: Path) -> GoldenSet:
    return GoldenSet.from_json(json.loads(path.read_text(encoding="utf-8")))


def save(golden: GoldenSet, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(golden.to_json(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _as_date(value: Any) -> date | None:
    return date.fromisoformat(str(value)) if value else None


__all__ = [
    "REFUSAL_AXES",
    "SCHEMA_VERSION",
    "Composition",
    "GoldenItem",
    "GoldenSet",
    "article_of",
    "load",
    "save",
    "validate_composition",
]
