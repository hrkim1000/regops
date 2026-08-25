"""The US paragraph ladder — shared by ``cfr_structured`` and ``usc_text``.

US drafting nests provisions by putting the designator **inline at the head of the text** —
``(a)``, then ``(1)``, then a letter or a roman numeral — rather than in separate elements the way
국가법령정보 hands over 조/항/호/목. Recovering that hierarchy from a flat run of paragraphs is the
same job for both US profiles, so it lives here once.

**The two conventions are not the same ladder, and that is why this module is parameterized rather
than copied.** They differ on both axes, and both differences are measured, not assumed:

*Order.* The CFR nests ``(a)(1)(i)(A)``; the USC nests ``(a)(1)(A)(i)(I)``. The USC order is not
inferred — govinfo declares it in its own markup, and the 2,500 designator-bearing heads in
21 U.S.C. chapter 9 agree: ``subsection-head`` is lowercase alpha 1,365 times, ``paragraph-head``
is a digit 1,603 times, ``subparagraph-head`` is uppercase alpha 863 times, ``clause-head`` is
lowercase roman 268 times, and ``subclause-head`` is uppercase roman every time it appears.

*Alphabet past z.* The CFR continues ``z → aa → ab → ac`` (base 26). The USC **doubles the
letter**: ``z → aa → bb → cc``. 21 U.S.C. 321 runs ``…y z aa bb cc dd ee ff gg hh ii jj kk ll mm nn
oo``, so reading it base-26 makes ``(bb)`` the 54th designator rather than the 28th, no open level
claims it, and every subsection from ``(bb)`` on is mis-nested.

**Sequence beats style, in both conventions.** For each designator the walker asks, from the
deepest open level outward, "is this the next label *here*?" — and only when no open level claims
it does it open a child. That single ordering is what disambiguates ``(i)``, which is both the
ninth letter and roman one: ``(h)`` → ``(i)`` continues a level, while ``(1)`` → ``(i)`` opens one.
The USC needs it twice over, because ``(ii)`` is both roman two and the doubled-letter designator
that follows ``(hh)`` — and chapter 9 uses it both ways.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from regops_shared.constants import ClauseKind

from ..canonicalize import normalize_text
from .model import ParsedClause

#: A paragraph designator at the head of a paragraph: ``(a)``, ``(1)``, ``(iv)``, ``(A)``, ``(II)``.
DESIGNATOR = re.compile(r"^\(([A-Za-z]{1,5}|\d{1,3})\)\s*")

#: The same token, anchored wherever it is asked for, so a run can be walked without re-slicing.
_TOKEN = re.compile(r"\(([A-Za-z]{1,5}|\d{1,3})\)")

#: A run longer than this is prose that happens to open with brackets, not a nesting.
_MAX_RUN: Final[int] = 5


def designator_run(text: str) -> list[str]:
    """The designators opening a paragraph — usually one, sometimes several.

    US drafting routinely starts a level and its first child on the same line:
    ``(3)(A) Except as provided in subparagraph (B)…`` is paragraph 3 *and* subparagraph A, and
    ``(i)(I) the food's advertising…`` is a clause and its first subclause. Reading only the leading
    token loses the intermediate level, and then the *next* designator has no open level to
    continue — in 21 U.S.C. 334 that pushed every nested ``(i)`` up to subsection level, where it
    collided with the section's real subsection ``(i)``.

    **Adjacency is what makes this safe.** Each token after the first must begin exactly where the
    previous one ended, so ``(a) The term "pesticide" (as defined) means…`` yields ``["a"]`` — the
    parenthetical is prose, and prose has a space in front of it.
    """
    tokens: list[str] = []
    position = 0
    while (match := _TOKEN.match(text, position)) is not None and len(tokens) < _MAX_RUN:
        tokens.append(match.group(1))
        position = match.end()
    return tokens


_ROMAN_VALUES: Final[dict[str, int]] = {
    "i": 1,
    "v": 5,
    "x": 10,
    "l": 50,
    "c": 100,
    "d": 500,
    "m": 1000,
}


class Style:
    """The designator alphabets. Which ones a ladder uses, and in what order, is per-convention."""

    LOWER_ALPHA = "lower_alpha"  # (a)
    DIGIT = "digit"  # (1)
    LOWER_ROMAN = "lower_roman"  # (i)
    UPPER_ALPHA = "upper_alpha"  # (A)
    UPPER_ROMAN = "upper_roman"  # (I)
    DOUBLED_LOWER = "doubled_lower"  # (aa) — the USC *item* level, which starts at a doubled letter
    DOUBLED_UPPER = "doubled_upper"  # (AA) — the USC *subitem* level below it


def roman_to_int(token: str) -> int | None:
    """``iv`` → 4. ``None`` when the token is not well-formed roman."""
    total = previous = 0
    for char in reversed(token.lower()):
        value = _ROMAN_VALUES.get(char)
        if value is None:
            return None
        total += -value if value < previous else value
        previous = max(previous, value)
    return total or None


def base26_alpha(token: str) -> int | None:
    """``a`` → 1, ``aa`` → 27, ``ab`` → 28 — the way the **CFR** continues past ``z``."""
    if not token.isalpha():
        return None
    total = 0
    for char in token.lower():
        total = total * 26 + (ord(char) - ord("a") + 1)
    return total


def doubled_only(token: str) -> int | None:
    """``aa`` → 1, ``bb`` → 2 — a level whose designators *begin* at a doubled letter.

    Not the same function as :func:`doubled_alpha`, and the difference is the whole reason both
    exist. A USC **subsection** runs ``a … z aa bb``, so ``(aa)`` is its 27th. A USC **item** — the
    level below subclause ``(I)`` — has no single-letter rung at all and opens *at* ``(aa)``, so
    there ``(aa)`` is the 1st. 21 U.S.C. 355 uses both, and the indentation govinfo publishes says
    which is which: the item ``(aa)`` sits in ``statutory-body-4em``, four levels in.

    Nothing disambiguates them by token, so nothing tries to. Sequence does it — see
    :meth:`Ladder.depth_for`.
    """
    if len(token) != 2 or not token.isalpha() or token[0] != token[1]:
        return None
    return ord(token[0].lower()) - ord("a") + 1


def doubled_alpha(token: str) -> int | None:
    """``a`` → 1, ``aa`` → 27, ``bb`` → 28 — the way the **USC** continues past ``z``.

    A mixed token such as ``ab`` is not a designator in this convention and returns ``None`` rather
    than a plausible number, so an unexpected label costs its nesting instead of silently landing at
    a position the authority never used.
    """
    if not token.isalpha():
        return None
    lowered = token.lower()
    if len(set(lowered)) != 1:
        return None
    return 26 * (len(lowered) - 1) + (ord(lowered[0]) - ord("a") + 1)


@dataclass(frozen=True, slots=True)
class Ladder:
    """One drafting convention: the order of the levels, and how its letters count."""

    #: Style per depth, outermost first. The last entry repeats for anything deeper.
    styles: tuple[str, ...]
    #: How this convention numbers alphabetic designators past ``z``.
    alpha_to_int: Callable[[str], int | None]

    def style_at(self, depth: int) -> str:
        return self.styles[depth] if depth < len(self.styles) else self.styles[-1]

    def index_in(self, token: str, style: str) -> int | None:
        if style == Style.DIGIT:
            return int(token) if token.isdigit() else None
        if style == Style.LOWER_ROMAN:
            return roman_to_int(token) if token.islower() else None
        if style == Style.UPPER_ROMAN:
            return roman_to_int(token) if token.isupper() else None
        if style == Style.LOWER_ALPHA:
            return self.alpha_to_int(token) if token.isalpha() and token.islower() else None
        if style == Style.UPPER_ALPHA:
            return self.alpha_to_int(token) if token.isalpha() and token.isupper() else None
        if style == Style.DOUBLED_LOWER:
            return doubled_only(token) if token.islower() else None
        if style == Style.DOUBLED_UPPER:
            return doubled_only(token) if token.isupper() else None
        return None

    def successor_of(self, token: str, style: str, previous: str | None) -> bool:
        """Is ``token`` the next label after ``previous`` in ``style``? See the module docstring."""
        if previous is None:
            return self.index_in(token, style) == 1
        prior = self.index_in(previous, style)
        current = self.index_in(token, style)
        return prior is not None and current == prior + 1

    def depth_for(self, token: str, stack: list[tuple[str, str, int]]) -> int:
        """Which level does this designator belong to — an open one, or a new child?

        Walking the open levels from the inside out is the whole disambiguation.
        """
        for depth in range(len(stack) - 1, -1, -1):
            label, style, _ = stack[depth]
            if self.successor_of(token, style, label.strip("()")):
                return depth

        child_depth = len(stack)
        if self.index_in(token, self.style_at(child_depth)) == 1:
            return child_depth

        # Neither a successor nor a well-formed first child — the authority's sequence broke.
        # Address it at the level whose alphabet it does match, so an unexpected designator costs
        # its nesting rather than the provision.
        for depth in range(len(stack), -1, -1):
            if self.index_in(token, self.style_at(depth)) is not None:
                return depth
        return child_depth

    def segment_paragraphs(
        self, paragraphs: list[str], *, prefix: tuple[str, ...], clauses: list[ParsedClause]
    ) -> None:
        """Turn a flat run of paragraph texts into a nested clause tree, by designator sequence.

        A paragraph with no designator is not an error: a section commonly opens with an unlabelled
        paragraph, and 21 CFR 820.35 does.
        """
        #: (path segment, style, index into ``clauses``) per open level, outermost first.
        stack: list[tuple[str, str, int]] = []

        for text in paragraphs:
            tokens = designator_run(text)
            if not tokens:
                _append_unlabelled(text, prefix=prefix, stack=stack, clauses=clauses)
                continue

            for position, token in enumerate(tokens):
                depth = self.depth_for(token, stack)
                del stack[depth:]

                segment = f"({token})"
                parent_index = stack[-1][2] if stack else None
                clauses.append(
                    ParsedClause(
                        path_segments=(*prefix, *(level[0] for level in stack), segment),
                        # Only the innermost designator of a run has text of its own. The levels
                        # above it carry their own label, which is the truth — paragraph (3) of
                        # ``(3)(A) Except as provided…`` states nothing except that its content is
                        # its subparagraphs — and it keeps a citation to that level resolvable
                        # instead of addressing a provision that has no row.
                        text=text if position == len(tokens) - 1 else segment,
                        kind=ClauseKind.PROSE,
                        parent_index=parent_index,
                    )
                )
                stack.append((segment, self.style_at(len(stack)), len(clauses) - 1))


def _append_unlabelled(
    text: str,
    *,
    prefix: tuple[str, ...],
    stack: list[tuple[str, str, int]],
    clauses: list[ParsedClause],
) -> None:
    """An undesignated paragraph continues whatever is open, or is the section's own lead text."""
    if stack:
        index = stack[-1][2]
        clauses[index].text = normalize_text(f"{clauses[index].text}\n{text}")
        return
    if clauses and clauses[-1].path_segments == prefix:
        clauses[-1].text = normalize_text(f"{clauses[-1].text}\n{text}")
        return
    clauses.append(ParsedClause(path_segments=prefix, text=text, kind=ClauseKind.PROSE))


#: The CFR ladder repeats after four levels: (a)(1)(i)(A)(1)(i)…
CFR = Ladder(
    styles=(
        Style.LOWER_ALPHA,
        Style.DIGIT,
        Style.LOWER_ROMAN,
        Style.UPPER_ALPHA,
        Style.DIGIT,
        Style.LOWER_ROMAN,
    ),
    alpha_to_int=base26_alpha,
)

#: The USC ladder, seven deep: subsection, paragraph, subparagraph, clause, subclause, item,
#: subitem. govinfo's ``*-head`` classes name the first five; the last two never appear as heads and
#: were read off the indentation instead — 21 U.S.C. 355 nests ``(A)`` at ``statutory-body-1em``,
#: ``(i)`` at ``2em``, ``(I)`` at ``3em`` and ``(aa)`` at ``4em``, with ``(AA)`` below that.
USC = Ladder(
    styles=(
        Style.LOWER_ALPHA,
        Style.DIGIT,
        Style.UPPER_ALPHA,
        Style.LOWER_ROMAN,
        Style.UPPER_ROMAN,
        Style.DOUBLED_LOWER,
        Style.DOUBLED_UPPER,
    ),
    alpha_to_int=doubled_alpha,
)


__all__ = [
    "CFR",
    "DESIGNATOR",
    "USC",
    "Ladder",
    "Style",
    "base26_alpha",
    "doubled_alpha",
    "doubled_only",
    "roman_to_int",
]
