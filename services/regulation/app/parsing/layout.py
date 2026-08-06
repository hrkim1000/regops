"""Undoing fixed-width line wrapping without inventing text.

Annex content arrives as **fixed-width plain text**: box-drawing tables padded to column widths, and
prose hard-wrapped to a page width. Reassembling a wrapped cell is where a table parser silently
corrupts data, because the wrap point does not say whether a space was there.

    │글루타랄(펜탄       │      ← mid-word wrap: a space here gives "글루타랄(펜탄 -1,5-디알)"
    │-1,5-디알)          │
    │에어로졸(스프레   │      ← also mid-word
    │이에 한함)        │
    │제품에는          │      ← wrapped at a space: joining without one gives "한함)제품에는"
    │사용금지          │

Neither "always join" nor "always space" is right, and both are wrong on real ingredient names —
which are exactly the values exact-match lookup keys on (ADR-0006 decision 3).

**The rule used here is the formatter's own rule, run backwards.** A fixed-width formatter breaks a
line only when the next token will not fit in the space left. So: measure the slack the fragment
left in its cell, and measure the first token of the next fragment. If the token could not have
fitted, the break was forced and the fragments join directly; if it would have fitted, the break was
deliberate and a space is restored.

Verified against every case above and against the 별표 2 보존제 table as a whole. Widths are
**display** columns, not characters — a Hangul syllable occupies two — or every measurement is out
by a factor of nearly two on Korean text.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Sequence

#: East Asian Wide and Fullwidth characters occupy two terminal columns; the authority's formatter
#: pads to those, so any arithmetic on character counts is wrong for Korean.
_WIDE = frozenset("WF")


def display_width(text: str) -> int:
    """Terminal column count, counting East Asian Wide/Fullwidth as 2."""
    return sum(2 if unicodedata.east_asian_width(ch) in _WIDE else 1 for ch in text)


def _first_token_width(text: str) -> int:
    """Width of the leading run of non-space characters — what the formatter had to fit."""
    token = text.lstrip()
    cut = token.find(" ")
    return display_width(token if cut < 0 else token[:cut])


#: Characters after which a **forced** break loses nothing. Korean permits a line break between any
#: two syllables, so a wrap after Hangul is ordinary character-level wrapping and loses no space.
#: A hyphen is a hyphenation point, and an opening bracket binds to what follows.
_NO_SPACE_AFTER = frozenset("-–—(（[［{｛「『")


def _joins_without_space(previous: str) -> bool:
    """Did a forced break after ``previous`` swallow a space?

    Latin and digit runs have no break opportunity inside them: a formatter can only break such a
    run where a space or a separator already was. So a forced break ending in ``0`` or ``/`` means a
    space was absorbed into the padding, while one ending in a Hangul syllable means none was.

    Without this, ``16807-48-0 /`` + ``520-45-6`` renders as ``16807-48-0 /520-45-6`` — wrong in a
    CAS column, which is exactly what exact-match lookup keys on.
    """
    tail = previous.rstrip()
    if not tail:
        return True
    last = tail[-1]
    return unicodedata.east_asian_width(last) in _WIDE or last in _NO_SPACE_AFTER


def join_wrapped(fragments: Sequence[str]) -> str:
    """Reassemble fixed-width fragments of one cell or paragraph into a single line.

    Each fragment is the **raw** slice including its trailing padding — the padding is the evidence,
    so stripping before calling this throws away the only signal available.

    A fragment that is exactly empty (an empty cell on a continuation line) contributes nothing. A
    fragment of ``None`` marks a sub-row rule inside the cell — a genuine boundary the authority
    drew, joined as a hard line break rather than guessed at.
    """
    parts = [f for f in fragments if f is not None and f.strip()]
    if not parts:
        return ""

    width = max(display_width(f) for f in fragments if f is not None)
    out = parts[0].strip()

    for index in range(1, len(parts)):
        previous, current = parts[index - 1], parts[index]
        slack = width - display_width(previous.rstrip())
        # Could the next fragment's first token have fitted on the previous line? If yes, the
        # formatter chose to break there, so the break stands for a space. If no, it was forced —
        # and then only a Hangul or hyphen tail means no space was lost.
        forced = slack < _first_token_width(current)
        separator = "" if forced and _joins_without_space(previous) else " "
        out += separator + current.strip()

    return out


def join_cell(fragments: Sequence[str | None]) -> str:
    """:func:`join_wrapped` for a table cell, honouring sub-row rules as hard breaks.

    ``None`` in ``fragments`` is a partial rule (``├────┼────┤`` drawn inside a row) splitting one
    logical cell into stacked values — two CAS numbers against one 원료명. That is a boundary the
    authority drew explicitly, so it becomes a newline instead of being run together.
    """
    groups: list[list[str]] = [[]]
    for fragment in fragments:
        if fragment is None:
            groups.append([])
        elif fragment.strip():
            groups[-1].append(fragment)

    rendered = [join_wrapped(group) for group in groups if group]
    return "\n".join(part for part in rendered if part)


__all__ = ["display_width", "join_cell", "join_wrapped"]
