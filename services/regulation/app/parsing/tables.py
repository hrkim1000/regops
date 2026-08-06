"""Box-drawing table mode. **Mechanical and deterministic — no LLM in the parsing path.**

The prohibited and restricted ingredient lists carrying most `mfds_cosmetic` obligations arrive as
fixed-width box-drawing text inside ``별표내용``, and the same shape appears on the SaMD side in
의료기기 기준규격. That is why table mode is a *content* strategy used by both domains rather than a
Cosmetic branch (ADR-0004 decision 3).

    ┌──────────┬─────────┬───────┐
    │원    료    명      │사 용 한 도       │CAS No.       │   ← header row
    ├──────────┼─────────┼───────┤
    │글루타랄(펜탄       │0.1%              │111-30-8      │   ← one logical row,
    │-1,5-디알)          │                  │              │     three physical lines
    ├──────────┼─────────┼───────┤

Two things make this harder than splitting on a delimiter, and both are handled here:

- **A logical row spans several physical lines.** Rows are delimited by ``├──┼──┤`` rules, never by
  newlines. Counting lines overstates the row count by roughly 16×, which is how "tens of thousands
  of rows per 고시" got into circulation before anyone measured it (ADR-0014).
- **Column boundaries do not line up by character index.** Border characters are East Asian Wide and
  ASCII padding is not, so the rule line and the content lines have different character lengths for
  the same layout. Splitting on ``│`` avoids the problem entirely — cell *count* is the invariant,
  and it is validated against the header rather than assumed.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field

from .layout import join_cell

#: Whitespace between two East Asian Wide characters. Korean table headers are letter-spaced for
#: visual justification — ``원    료    명`` is 원료명 — so the gaps are typography, not content.
_WIDE_GAP = re.compile(r"(?<=[ᄀ-ᇿ㄰-㆏가-힯])\s+(?=[가-힯])")
_SPACE_RUN = re.compile(r"\s+")


def normalize_label(raw: str) -> str:
    """``원    료    명`` → ``원료명``, but ``CAS No.`` keeps its space.

    Header labels become **jsonb keys** (ADR-0014 decision 4), so they are what an exact-match
    lookup names. Collapsing every space would give ``CASNo.``; collapsing none would require a
    caller to reproduce the authority's justification spacing to read a column. Only gaps *between
    Hangul syllables* are typography, and only those are removed.
    """
    collapsed = _WIDE_GAP.sub("", unicodedata.normalize("NFC", raw).strip())
    return _SPACE_RUN.sub(" ", collapsed).strip()


#: Characters a rule line may contain. A line built only from these (plus space) draws structure;
#: anything else carries content.
_RULE_CHARS = frozenset("┌┬┐├┼┤└┴┘─━┏┳┓┣╋┫┗┻┛")

#: Characters that separate cells on a content line. ``├ ┼ ┤`` are here alongside ``│`` because a
#: **partial** rule is drawn with them *inside* an otherwise ordinary row:
#:
#:     │디온) 및 그 염류    │        │사용금지          ├───────┼─────┤
#:
#: Splitting on ``│`` alone leaves ``├───────┼─────┤`` glued to the last text cell, so the rule
#: characters land in a citable value. Treating them as separators splits the line into the right
#: number of cells and lets the rule fragments be recognised as sub-row boundaries.
_VERTICAL = frozenset("│┃|├┼┤┣╋┫")


@dataclass(slots=True)
class Table:
    """One box-drawing table: an ordered header and its logical rows."""

    header: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    #: Line index in the source content where the table's top rule sat — used to interleave tables
    #: with the prose around them in document order.
    start_line: int = 0

    def as_mapping(self, row: Sequence[str]) -> dict[str, str]:
        """Zip one row against the header, tolerating a ragged tail.

        A row with fewer cells than the header is padded rather than rejected: merged trailing cells
        are common and dropping the row would lose an obligation. A row with *more* cells than the
        header keeps the surplus under a positional key, so nothing is silently discarded.
        """
        mapping: dict[str, str] = {}
        for index, label in enumerate(self.header):
            mapping[label] = row[index] if index < len(row) else ""
        for index in range(len(self.header), len(row)):
            mapping[f"col{index + 1}"] = row[index]
        return mapping


def is_rule(line: str) -> bool:
    """A line drawing only structure — no content."""
    stripped = line.strip()
    return bool(stripped) and "─" in stripped and set(stripped) <= _RULE_CHARS | {" ", "　"}


def _rule_role(line: str) -> str | None:
    """``top`` / ``mid`` / ``bottom`` for a full-width rule; ``None`` for anything else.

    A rule that begins with ``│`` is a *partial* rule splitting cells inside a row — a merged 원료명
    against two CAS numbers — not a row boundary. Treating it as one would shred a single obligation
    into several rows.
    """
    if not is_rule(line):
        return None
    stripped = line.strip()
    return {"┌": "top", "┏": "top", "├": "mid", "┣": "mid", "└": "bottom", "┗": "bottom"}.get(
        stripped[0]
    )


def _is_content(line: str) -> bool:
    return bool(set(line) & _VERTICAL) and not is_rule(line)


def _split_cells(line: str) -> list[str | None]:
    """Split one content line into raw cell slices, padding included.

    Padding is deliberately preserved — :func:`~.layout.join_cell` needs it to tell a mid-word wrap
    from a deliberate line break. A slice that is itself a rule fragment (from a partial rule drawn
    inside the row) becomes ``None``, marking a sub-row boundary.
    """
    cells: list[str | None] = []
    for raw in _split_on_vertical(line):
        stripped = raw.strip()
        if stripped and set(stripped) <= _RULE_CHARS:
            cells.append(None)
        else:
            cells.append(raw)
    return cells


def _split_on_vertical(line: str) -> list[str]:
    """Split on any vertical rule character, dropping the empty edges outside the table frame."""
    parts: list[str] = []
    current: list[str] = []
    for char in line:
        if char in _VERTICAL:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    parts.append("".join(current))
    # The frame produces an empty slice before the first │ and after the last one.
    if parts and not parts[0].strip():
        parts = parts[1:]
    if parts and not parts[-1].strip():
        parts = parts[:-1]
    return parts


def _assemble(buffered: list[list[str | None]]) -> list[str]:
    """Turn the physical lines of one logical row into one value per column."""
    if not buffered:
        return []
    width = max(len(line) for line in buffered)
    columns: list[list[str | None]] = [[] for _ in range(width)]
    for line in buffered:
        for index in range(width):
            columns[index].append(line[index] if index < len(line) else "")
    return [join_cell(column) for column in columns]


def find_tables(content: str) -> list[Table]:
    """Extract every box-drawing table from an annex body, in document order.

    The first logical row after the top rule is taken as the header. That is right for every table
    observed in the gated corpus; where it is wrong the header simply becomes column labels that
    read like data, which degrades lookup rather than losing content.
    """
    return list(_scan(content.split("\n")))


def _scan(lines: Sequence[str]) -> Iterator[Table]:
    table: Table | None = None
    buffered: list[list[str | None]] = []

    for index, line in enumerate(lines):
        role = _rule_role(line)

        if role == "top":
            if table is not None and (table.header or table.rows):
                yield table  # a table that abuts the next one without closing its frame
            table = Table(start_line=index)
            buffered = []
            continue

        if table is None:
            continue

        if role in {"mid", "bottom"}:
            row = _assemble(buffered)
            buffered = []
            if any(cell.strip() for cell in row):
                if not table.header:
                    table.header = [normalize_label(cell) for cell in row]
                else:
                    table.rows.append(row)
            if role == "bottom":
                if table.header or table.rows:
                    yield table
                table = None
            continue

        if _is_content(line):
            buffered.append(_split_cells(line))
        elif line.strip() and buffered:
            # Prose between the rules of an open table — the frame was not closed. Flush what we
            # have rather than absorbing the prose into a cell.
            row = _assemble(buffered)
            buffered = []
            if any(cell.strip() for cell in row):
                if table.header:
                    table.rows.append(row)
                else:
                    table.header = [normalize_label(cell) for cell in row]

    if table is not None and (table.header or table.rows):
        yield table


def render_row(mapping: dict[str, str]) -> str:
    """A row as citable text: ``label: value`` pairs, one per line.

    A row must be readable from its ``text`` alone — an RA opening a citation should not need a
    client that understands the column map (ADR-0014 decision 4).
    """
    return "\n".join(f"{label}: {value}" for label, value in mapping.items() if value.strip())


__all__ = ["Table", "find_tables", "is_rule", "render_row"]
