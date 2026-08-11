"""Submission requirements: *what must be filed for this procedure* — derived, never stored.

A Korean procedural clause states the whole thing in one shape:

    ① … 별지 제1호서식의 신청서에 다음 각 호의 자료를 첨부하여 …에게 제출하여야 한다.
       1. 의료기기 제조(수입)업 허가증 사본
       2. 다음 각 목에 해당되는 자료
       3. 제2호에도 불구하고, 의료기기공동심사프로그램을 활용하는 경우 …

The 항 is the obligation and the 호 are the required documents — and phase 1.1 already parsed the
호 as **child clauses with their own `clause_path`**. So the document list is not something to
extract; it is something to *read*, and every item arrives citable. Measured over the gated corpus:
**102 procedures, 368 document items, 99% with their items already parsed.**

Three properties are why this module exists rather than an agent:

- **No LLM.** The item text *is* the document name. Nothing is generated, so there is nothing to
  hallucinate, no provenance to record and no human gate to pass — this is a pipeline in the read
  path, not an agent (ADR-0008).
- **Nothing is stored.** The whole result is a pure function of clauses. Storing it would create a
  second derived artefact to invalidate on re-parse, which is the bug `parse._invalidate_derived`
  exists to fix for diffs — 2,373 orphaned rows, observed. Re-parse changes clauses; the next read
  simply re-derives.
- **Conditions are never flattened.** This is the load-bearing one. 40% of these procedures and 18%
  of their items carry conditional language, so *"제출 서류 5종"* is a confidently wrong answer.
  Every condition travels verbatim on the item that carries it, and the requirement publishes
  machine-readable :class:`Caveat` codes saying why the list is not a settled checklist.

**Which conditions apply to a given company is not answered here and must not be.** Applicability is
Compliance-owned and tenant-scoped (ADR-0007, phase 2.2); `regulation` holds shared reference data
and has no product context. This module says *what the regulation requires and under what stated
conditions* — deciding which of them bind a particular product is a different question with a
different owner.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from regops_shared.constants import ClauseKind
from regops_shared.models import Clause

# --- the detection vocabulary ----------------------------------------------------------------
#
# Every pattern below was measured against the archived corpus before being committed, because the
# precision of this feature *is* these regexes. A looser first attempt matched 341 clauses and a
# stricter one 92; the difference was almost entirely `다음 각 호의 사항` — enumerations of matters
# to observe rather than documents to file. The set below yields **102 procedures**, and the two
# negative patterns are what earn that number.

#: The enumeration marker. Without it the 호 are not a list and there is nothing to read.
_ENUMERATES: Final[re.Pattern[str]] = re.compile(r"다음 각 호")

#: What makes the enumerated things *documents*. A procedure that enumerates 기준 or 요건 is a
#: different kind of clause and belongs to IR extraction, not here.
_DOCUMENT_NOUN: Final[re.Pattern[str]] = re.compile(
    r"서류|자료|서면|증명서|사본|신청서|보고서|계획서"
)

#: A **positive** filing duty. Conjugations matter for the same reason they do in the modal
#: inventory: `첨부하여` and `첨부해` are the same act, and matching only the citation form would
#: miss most of the corpus.
_SUBMIT_VERB: Final[re.Pattern[str]] = re.compile(
    r"첨부하(여|아|여야|은)|첨부해|제출하여야|제출해야|제출하여|갖추어|구비하(여|아)"
)

#: Enumerations that are *not* document lists. Measured counter-examples, all real:
#: "다음 각 호의 **어느 하나**에 해당하는 의료기기", "다음 각 호의 **사항**과 관련된 자료의 제출".
#: Both match the three positive patterns above and neither is a list of things to file.
_NOT_A_DOCUMENT_LIST: Final[re.Pattern[str]] = re.compile(
    r"다음 각 호의\s*(사항|기준|요건|어느 하나|경우)"
)

#: Exemptions. "제1항의 일부 자료를 **제출하지 아니할 수 있다**" states what may be *omitted*, and
#: reading it as a requirement would invert the clause — the worst failure this module could have.
_EXEMPTION: Final[re.Pattern[str]] = re.compile(r"(제출|첨부)하지\s*(아니|않)|면제(한다|할 수)")

#: The prescribed form, captured **verbatim as written**. It is deliberately *not* resolved to a
#: Document: resolving a cross-reference is a separate deterministic stage (ADR-0010 decision 7,
#: phase 2.1), and a guessed resolution here would attach evidence nobody verified.
_FORM_REFERENCE: Final[re.Pattern[str]] = re.compile(r"별지\s*제\s*\d+(?:호의\d+)?\s*호?서식")

#: Where the filing goes — the ``에게`` that a submission verb follows.
#:
#: Only the *anchor* is a regex. A capture group here cannot work: ``re.search`` matches leftmost,
#: so any pattern permitting spaces starts as early as it can and returns
#: "각 호의 자료를 첨부하여 품질관리심사기관의 장" for "품질관리심사기관의 장". The phrase is
#: recovered by walking tokens backwards instead (:func:`_recipient`), which is both correct and
#: readable — the alternative is a regex nobody can verify by reading.
_RECIPIENT_ANCHOR: Final[re.Pattern[str]] = re.compile(r"에게\s*(?:제출|신청|보고|통보)")

#: Token endings that close the *previous* phrase, so the recipient begins after them. Object and
#: subject markers, and connective verb endings. ``의`` is deliberately absent: it is genitive and
#: belongs *inside* the recipient — "품질관리심사기관**의** 장" is one title, not two phrases.
_PHRASE_BOUNDARY: Final[tuple[str, ...]] = (
    "를",
    "을",
    "여",
    "아",
    "고",
    "서",
    "며",
    "은",
    "는",
    "이",
    "가",
    "도",
    "만",
    "로",
    "와",
    "과",
    "및",
    "에",
    "서는",
)

#: Connectors that join *alternative* recipients into one slot rather than ending the phrase.
#: "식품의약품안전처장 **또는** 기술문서심사기관의 장에게" names one destination with two options,
#: and treating 또는 as a boundary (it ends in 는, like a topic marker) drops the first of them —
#: observed live on 의료기기법 시행규칙 제9조제3항.
_RECIPIENT_CONNECTOR: Final[tuple[str, ...]] = ("또는", "및", "이나", "나")

#: Recipients are short titles — 식품의약품안전처장, 품질관리심사기관의 장. Six tokens covers the
#: longest real form, "식품의약품안전처장 또는 기술문서심사기관의 장"; past that the walk has left
#: the title and is eating the sentence.
_RECIPIENT_MAX_TOKENS: Final[int] = 6

#: Language that makes an item or a procedure conditional.
#:
#: **Bare `경우`, not `경우에는`.** A narrower first version keyed on the inflected forms and missed
#: 29 of 370 real items — "자격증을 잃어버린 **경우**: 분실 사유서", "(폐기한 **경우**에만 해당)".
#: Every one is plainly conditional, and missing a condition is the one direction this module must
#: not fail in: an unflagged conditional item is a flattened condition, which is the failure the
#: whole design exists to prevent. Widening moved item coverage 17% -> 25%, so the flag still
#: discriminates — three quarters of items remain unconditional.
#:
#: `다만` is a proviso marker and carries as much weight as the rest: a clause's exceptions are
#: usually where its real scope lives.
_CONDITIONAL: Final[re.Pattern[str]] = re.compile(
    r"에도 불구하고|경우|한정한|제외한|다만|에 한하여|만 해당"
)

#: The item defers its content to another instrument, so the list is incomplete at this level.
_DELEGATION: Final[re.Pattern[str]] = re.compile(
    r"(대통령령|총리령|부령|고시|훈령|예규)(?:으)?로\s*정(?:하는|한다)"
)

#: The item branches into 목. Its children carry the real detail.
_HAS_SUB_ITEMS: Final[re.Pattern[str]] = re.compile(r"다음 각 목")

#: An enabling reference into a different instrument — "법 제8조제3항에 따라". The obligation and
#: its document list routinely live in different documents (법 → 시행규칙), so a list read from one
#: of them alone can be incomplete.
_CROSS_INSTRUMENT: Final[re.Pattern[str]] = re.compile(r"법\s*제\d+조|「[^」]{2,40}」\s*제\d+조")


class Caveat(StrEnum):
    """Why a requirement must not be read as a settled checklist.

    Machine-readable rather than prose so a caller can *refuse to render a checkbox* on the strength
    of it. A caveat expressed only in a footnote is one the UI can ignore, and the whole failure
    this module guards against is a conditional list presented as a definitive one.
    """

    CONDITIONAL_PROCEDURE = "conditional_procedure"  # the 항 itself is qualified
    CONDITIONAL_ITEMS = "conditional_items"  # some items apply only in stated cases
    DELEGATED_ITEMS = "delegated_items"  # some items defer to another instrument
    NESTED_ITEMS = "nested_items"  # some items expand into 목
    CROSS_INSTRUMENT = "cross_instrument"  # the enabling clause is in another law
    NO_ITEMS_PARSED = "no_items_parsed"  # the list is stated inline, not as child clauses


@dataclass(frozen=True, slots=True)
class RequiredDocument:
    """One thing that must be filed. Text is **verbatim** — this is evidence, not a summary."""

    clause_id: uuid.UUID
    clause_path: str
    ordinal: int
    text: str
    #: **The signal a consumer must check.** True whenever the item applies only in stated cases —
    #: including when the whole item is one conditional sentence, which is most of them.
    conditional: bool
    #: The condition phrase, verbatim, *only when it is narrower than the item itself*. Many items
    #: are conditional end to end ("소재지 변경의 경우: …서류"), and echoing the whole text back
    #: here would duplicate it while adding nothing. ``None`` therefore does **not** mean
    #: unconditional — :attr:`conditional` means that, and this is the courtesy detail beside it.
    condition_text: str | None
    #: Names another instrument instead of a document — the real content lives elsewhere.
    delegates: bool
    #: Expands into 목; the children hold the detail this level only gestures at.
    has_sub_items: bool
    sub_item_paths: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SubmissionRequirement:
    """One procedure and what it requires filed."""

    clause_id: uuid.UUID
    clause_path: str
    heading: str | None
    #: The 항 verbatim. The reader has to be able to check the derivation against the source.
    text: str
    #: "별지 제1호서식" as the clause writes it — a string, not a resolved Document (see above).
    form_reference: str | None
    recipient: str | None
    documents: list[RequiredDocument] = field(default_factory=list)
    caveats: tuple[Caveat, ...] = ()

    @property
    def is_definitive(self) -> bool:
        """Whether this list may be presented as a complete, unconditional set. Usually false."""
        return not self.caveats


def derive(session: Session, version_id: uuid.UUID) -> list[SubmissionRequirement]:
    """Read every submission requirement stated by one version, in document order.

    One pass over the version's clauses plus one lookup for 목 children. Nothing is written.
    """
    clauses = list(
        session.scalars(
            select(Clause).where(Clause.document_version_id == version_id).order_by(Clause.ordinal)
        )
    )
    by_parent: dict[uuid.UUID, list[Clause]] = {}
    for clause in clauses:
        if clause.parent_clause_id is not None:
            by_parent.setdefault(clause.parent_clause_id, []).append(clause)

    out: list[SubmissionRequirement] = []
    for clause in clauses:
        if not _is_submission_clause(clause):
            continue
        out.append(_build(clause, by_parent))
    return out


def _is_submission_clause(clause: Clause) -> bool:
    """Does this clause state a positive duty to file an enumerated set of documents?"""
    if clause.kind is not ClauseKind.PROSE:
        return False
    text = clause.text or ""
    return bool(
        _ENUMERATES.search(text)
        and _DOCUMENT_NOUN.search(text)
        and _SUBMIT_VERB.search(text)
        and not _NOT_A_DOCUMENT_LIST.search(text)
        and not _EXEMPTION.search(text)
    )


def _build(clause: Clause, by_parent: dict[uuid.UUID, list[Clause]]) -> SubmissionRequirement:
    items = [
        _document(child, by_parent)
        for child in sorted(by_parent.get(clause.id, []), key=lambda c: c.ordinal)
    ]

    caveats: list[Caveat] = []
    if _CONDITIONAL.search(clause.text or ""):
        caveats.append(Caveat.CONDITIONAL_PROCEDURE)
    if any(item.conditional for item in items):
        caveats.append(Caveat.CONDITIONAL_ITEMS)
    if any(item.delegates for item in items):
        caveats.append(Caveat.DELEGATED_ITEMS)
    if any(item.has_sub_items for item in items):
        caveats.append(Caveat.NESTED_ITEMS)
    if _CROSS_INSTRUMENT.search(clause.text or ""):
        caveats.append(Caveat.CROSS_INSTRUMENT)
    if not items:
        # The clause enumerates but its 호 did not become child clauses — the list is inline in the
        # body. Reporting the procedure with an empty list would read as "nothing is required".
        caveats.append(Caveat.NO_ITEMS_PARSED)

    return SubmissionRequirement(
        clause_id=clause.id,
        clause_path=clause.clause_path,
        heading=clause.heading,
        text=clause.text,
        form_reference=_first(_FORM_REFERENCE, clause.text),
        recipient=_recipient(clause.text),
        documents=items,
        caveats=tuple(caveats),
    )


def _document(clause: Clause, by_parent: dict[uuid.UUID, list[Clause]]) -> RequiredDocument:
    text = clause.text or ""
    children = sorted(by_parent.get(clause.id, []), key=lambda c: c.ordinal)
    return RequiredDocument(
        clause_id=clause.id,
        clause_path=clause.clause_path,
        ordinal=clause.ordinal,
        text=text,
        conditional=bool(_CONDITIONAL.search(text)),
        condition_text=_condition(text),
        delegates=bool(_DELEGATION.search(text)),
        has_sub_items=bool(children) or bool(_HAS_SUB_ITEMS.search(text)),
        sub_item_paths=tuple(child.clause_path for child in children),
    )


def _condition(text: str) -> str | None:
    """The condition sentence, verbatim — or ``None`` when it *is* the whole item.

    A sentence rather than the matched keyword: "제2호에도 불구하고" alone tells a reader nothing,
    and the point of keeping this is that a human can judge whether the condition applies.

    Returning ``None`` for a wholly conditional item is not a loss of information — the boolean
    already carries it — and it keeps the payload from shipping every item's text twice.
    """
    match = _CONDITIONAL.search(text)
    if match is None:
        return None
    # Sentence boundaries in this corpus are `.` followed by space, and 호 text is short enough that
    # the whole item is usually one sentence.
    start = text.rfind(". ", 0, match.start()) + 2 if ". " in text[: match.start()] else 0
    end = text.find(". ", match.end())
    phrase = text[start : end + 1 if end != -1 else None].strip()
    if not phrase:
        return None
    # Strip the leading 호 number before comparing — "1. …" and "…" are the same sentence.
    body = re.sub(r"^\s*\d+(?:의\d+)?\.\s*", "", text).strip()
    return None if phrase == body else phrase


def _recipient(text: str | None) -> str | None:
    """The authority a filing goes to — the title immediately before ``에게``.

    Walks tokens backwards from the anchor and stops at the first one that closes the previous
    phrase. "…다음 각 호의 자료를 첨부하여 품질관리심사기관의 장에게" stops at "첨부하여" and
    yields "품질관리심사기관의 장", where a leftmost regex match returns the whole tail.
    """
    match = _RECIPIENT_ANCHOR.search(text or "")
    if match is None:
        return None

    tokens = (text or "")[: match.start()].split()
    picked: list[str] = []
    for token in reversed(tokens[-_RECIPIENT_MAX_TOKENS:]):
        if token in _RECIPIENT_CONNECTOR:
            # Joins two alternative recipients; keep walking so both are captured.
            picked.append(token)
            continue
        if picked and token.endswith(_PHRASE_BOUNDARY):
            break
        picked.append(token)
        if token.endswith(_PHRASE_BOUNDARY) and not picked[:-1]:
            # The very first token back already ends a phrase — there is no title here.
            return None
    # A trailing connector means the walk stopped mid-join; it belongs to neither side.
    while picked and picked[-1] in _RECIPIENT_CONNECTOR:
        picked.pop()
    return " ".join(reversed(picked)) or None


def _first(pattern: re.Pattern[str], text: str | None) -> str | None:
    match = pattern.search(text or "")
    return re.sub(r"\s+", " ", match.group(0)).strip() if match else None


__all__ = [
    "Caveat",
    "RequiredDocument",
    "SubmissionRequirement",
    "derive",
]
