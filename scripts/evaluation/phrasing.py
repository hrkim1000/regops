"""How a golden question is worded, and what an "article" is — per **language**, never per cell.

The seeder was written against one corpus and inherited its shape without saying so: Korean question
templates, ``^제(\\d+)조`` for the article number, ``삭제`` for a provision with no content, and a
SQL regex matching only 조 paths. Pointed at an FDA cell, ``corpus.articles`` returns nothing at all
and every axis comes back empty.

**The key is the version's language, which is the seam the rest of the system already uses** —
``rule_set_for(domain, language)`` selects the extraction inventory, and
``document_versions.language`` selects the full-text configuration. Keying on authority or cell
would put a branch on who *wrote* the instrument, which is what ADR-0002 decision 3 forbids and
phase2.0a's falsifier exists to catch. Two English cells share this profile; a third needs no
change.

What is genuinely per-language and not merely translated:

``article_pattern``
    Which clause paths are the citable unit. Korean 조 end in ``조``; a CFR section and a USC
    section are both **path segments beginning with a digit** — ``820.35``, ``351``, ``350a–1``.
    Containers begin with a letter (``Subpart A``, ``Subchapter V``) and paragraphs with ``(``.

``vacant``
    A provision whose path exists and whose content does not. Korean says ``삭제``; the CFR says
    ``[Reserved]`` and the USC says ``Repealed.`` / ``Omitted`` / ``Transferred``. Measured against
    the live corpus on 2026-08-26, not guessed: those four strings cover every one of them.

``absent_article``
    A citable identifier the instrument provably does not have. ``제5조`` counts upward, so
    ``제{highest + 11}조`` is enough; a CFR section is ``820.45`` and its successor has to keep the
    Part, so the offset lands on the numeric tail and the stem is preserved.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

#: Trailing integer of an identifier, with whatever precedes it kept as the stem: ``820.45`` splits
#: to ``("820.", 45)`` and ``399`` to ``("", 399)``. A USC letter suffix (``321a``) has no trailing
#: integer of its own, so the section it belongs to is what is read.
_TRAILING_NUMBER: Final[re.Pattern[str]] = re.compile(r"^(?P<stem>.*?)(?P<number>\d+)\D*$")

_KO_ARTICLE: Final[re.Pattern[str]] = re.compile(r"^제(\d+)조")

#: A CFR or USC heading repeats its own identifier — ``§ 820.35 Control of records.`` and
#: ``§§ 820.20-820.30 [Reserved]``. A template that prints both reads "820.35 of 21 CFR Part 820
#: (§ 820.35 Control of records.)", so the identifier is stripped for display. Korean 조문제목 carry
#: no such prefix and are used as they are.
_EN_HEADING_PREFIX: Final[re.Pattern[str]] = re.compile(r"^\s*§+\s*[0-9][^\s]*(\s+to\s+[^\s]+)?\s*")


@dataclass(frozen=True, slots=True)
class Phrasing:
    """One language's question templates and citation conventions."""

    language: str
    #: POSIX regex handed to Postgres, matching the clause paths that are the citable unit.
    article_pattern: str
    #: Rotated so the set does not measure one phrasing. Not paraphrase — these are all identifier
    #: lookups, and pretending otherwise is what the conceptual axis exists to prevent.
    identifier_templates: tuple[str, ...]
    missing_templates: tuple[str, ...]
    deleted_template: str
    cross_template: str
    #: ``expected_answer`` for each refusal family. A refusal still has to say *which* refusal.
    absent_answer: str
    vacant_answer: str
    wrong_cell_answer: str
    #: ``expected_answer`` for an identifier lookup, given the clause heading.
    answer_for: Callable[[str], str]
    #: Does this heading mark a provision with no content to ask about?
    vacant: Callable[[str | None], bool]
    #: The heading as it should read inside a question, with any repeated identifier removed.
    display_heading: Callable[[str | None], str]
    #: The citable number, for ordering and for building one the instrument does not have.
    number_of: Callable[[str], int]
    #: An identifier past the end of the instrument, keeping its numbering convention.
    absent_article: Callable[[str, int], str]

    def article_segment(self, clause_path: str) -> str | None:
        """The citable segment of a path, or ``None`` if it holds none."""
        segments = [segment for segment in clause_path.split("/") if segment]
        for segment in segments:
            if self._is_article(segment):
                return segment
        return None

    def _is_article(self, segment: str) -> bool:
        if self.language == "ko":
            return segment.endswith("조") or "조의" in segment
        return bool(segment) and segment[0].isdigit()


def _ko_number(article: str) -> int:
    match = _KO_ARTICLE.match(article)
    return int(match.group(1)) if match else 0


def _en_number(article: str) -> int:
    match = _TRAILING_NUMBER.match(article)
    return int(match.group("number")) if match else 0


def _en_absent(highest_article: str, offset: int) -> str:
    """``820.45`` + 11 → ``820.56``; ``399`` + 11 → ``410``.

    The stem is kept because a CFR section number is not free-standing: ``56`` is not a section of
    part 820 and ``821.45`` is a different Part entirely — one that exists, which would turn a trap
    about a non-existent provision into a question about a real one in the wrong instrument.
    """
    match = _TRAILING_NUMBER.match(highest_article)
    if match is None:
        return f"{highest_article}-{offset}"
    return f"{match.group('stem')}{int(match.group('number')) + offset}"


#: ``삭제``, ``[Reserved]``, ``Repealed.``, ``Omitted``, ``Transferred`` — the authority saying the
#: address is real and the obligation is not.
_EN_VACANT: Final[tuple[str, ...]] = ("[reserved]", "repealed", "omitted", "transferred")


KOREAN = Phrasing(
    language="ko",
    article_pattern=r"(^|/)제[0-9]+조(의[0-9]+)?$",
    identifier_templates=(
        "「{title}」 {article}은(는) 무엇을 규정하고 있습니까?",
        "「{title}」 {article}({heading})의 내용을 알려주세요.",
        "「{title}」 {article}에 규정된 사항은 무엇입니까?",
        "{heading}에 관한 「{title}」 {article}의 규정 내용은?",
    ),
    missing_templates=(
        "「{title}」 {article}에 따른 제출 의무는 무엇입니까?",
        "「{title}」 {article}이(가) 정하는 기준을 알려주세요.",
    ),
    deleted_template="「{title}」 {article}은(는) 어떤 의무를 정하고 있습니까?",
    cross_template="「{title}」 {article}({heading})에 따른 의무는 무엇입니까?",
    absent_answer="확인 필요 — 해당 조문이 존재하지 않음",
    vacant_answer="확인 필요 — 삭제된 조문",
    wrong_cell_answer="확인 필요 — 이 셀의 규정이 아님",
    answer_for=lambda heading: f"{heading}에 관한 규정",
    vacant=lambda heading: not heading or "삭제" in heading,
    display_heading=lambda heading: (heading or "").strip(),
    number_of=_ko_number,
    absent_article=lambda highest, offset: f"제{_ko_number(highest) + offset}조",
)

ENGLISH = Phrasing(
    language="en",
    #: A section is a path segment starting with a digit. Containers start with a letter and
    #: paragraphs with "(", so this needs no list of container names to stay correct.
    article_pattern=r"(^|/)[0-9][^/]*$",
    identifier_templates=(
        "What does {article} of {title} require?",
        "What is set out in {article} of {title} ({heading})?",
        "Summarise the requirements of {article} of {title}.",
        "Under {title}, what does {article} provide on {heading}?",
    ),
    missing_templates=(
        "What must be submitted under {article} of {title}?",
        "What standard does {article} of {title} set?",
    ),
    deleted_template="What obligation does {article} of {title} impose?",
    cross_template="What is required by {article} of {title} ({heading})?",
    absent_answer="Needs verification — no such provision",
    vacant_answer="Needs verification — the provision is reserved or repealed",
    wrong_cell_answer="Needs verification — not a regulation of this cell",
    answer_for=lambda heading: f"Provision concerning {heading}",
    vacant=lambda heading: not heading or any(marker in heading.lower() for marker in _EN_VACANT),
    display_heading=lambda heading: _EN_HEADING_PREFIX.sub("", heading or "").strip().rstrip("."),
    number_of=_en_number,
    absent_article=_en_absent,
)

_BY_LANGUAGE: Final[dict[str, Phrasing]] = {KOREAN.language: KOREAN, ENGLISH.language: ENGLISH}


def for_language(language: str) -> Phrasing:
    """The phrasing for a version's language.

    **A missing language raises rather than falling back**, on the precedent ``rule_set_for`` set:
    a silent default would seed a Korean question set over an English corpus and report it as a
    measurement. An unseeded axis is visible; a plausible-looking wrong one is not.
    """
    try:
        return _BY_LANGUAGE[language]
    except KeyError:
        raise KeyError(
            f"no golden-set phrasing for language {language!r}; "
            f"known: {', '.join(sorted(_BY_LANGUAGE))}"
        ) from None


__all__ = ["ENGLISH", "KOREAN", "Phrasing", "for_language"]
