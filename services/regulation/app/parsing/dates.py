"""Effective dates: the authority's stated one, and the 부칙 phrase behind it.

[ADR-0016](../../../../docs/design/ADR-0016-pending-effect-versions.md) settles where the date comes
from. ``기본정보/시행일자`` states it outright for both 법령 and 행정규칙, so parsing 부칙 prose to
re-derive it would be a worse estimate of a fact already published. The 부칙 supplies the *phrase*,
and is the fallback for sources that state no date.

[ADR-0013](../../../../docs/design/ADR-0013-unresolvable-effective-dates.md) governs the rest: a
date that cannot be resolved to a calendar day stays **null**, and the raw phrase is retained. A
computed date is never written into ``effective_date``, because once there it is indistinguishable
from an authoritative one to retrieval, citation rendering and the superseded-citation queue.

The phrase is kept **whenever it was non-trivial**, not only when resolution failed — that is what
makes "we resolved this" and "we had nothing to resolve" distinguishable later, and what makes the
extraction rate measurable in phase 1.6 rather than inferred.
"""

from __future__ import annotations

import re
from datetime import date
from xml.etree.ElementTree import Element

from ..canonicalize import normalize_text
from ..connectors.law_go_kr import parse_authority_date

#: 제1조(시행일) and its variants — the 부칙 article that states application. Everything after it in
#: the same 부칙 is 경과조치 and is not about when the instrument bites.
_ENFORCEMENT_ARTICLE = re.compile(
    r"제\s*1\s*조\s*\(\s*시행일\s*\)(?P<body>.*?)(?=\n\s*제\s*2\s*조|\Z)",
    re.DOTALL,
)
#: A 부칙 with no article structure at all: "이 고시는 발령한 날부터 시행한다."
_BARE_ENFORCEMENT = re.compile(r"[^\n]*?(?:부터|날)\s*시행한다[^\n]*")


def envelope_effective_date(root: Element) -> date | None:
    """``기본정보/시행일자`` → a date. Authority-stated metadata, not an inference (ADR-0016)."""
    for element in root.iter("시행일자"):
        parsed = parse_authority_date(normalize_text(element.text or ""))
        if parsed:
            return parsed.date()
    return None


#: One ``날짜:별표목록`` group. A following group starts with another 8-digit date, and no annex
#: label begins with eight digits, so the lookahead is unambiguous.
_ANNEX_DATE_GROUP = re.compile(r"(?=\d{8}\s*:)")
_ANNEX_DATE_HEAD = re.compile(r"^(\d{8})\s*:\s*(.*)$", re.DOTALL)


def annex_effective_dates(root: Element) -> dict[str, date]:
    """``별표시행일자문자열`` → ``{"별표9": date, "서식39": date, …}``.

    **This is the field ADR-0012's whole rationale rests on** — *"the authority publishes
    별표시행일자문자열 … precisely because annexes move on their own schedule"* — and it lives in
    ``기본정보``, not in the ``별표단위`` it describes. Its shape is a date followed by the annexes
    that take effect on it:

        20260701:별표7의2,별표7의3,별표9,별표10,서식12의2,서식38의4

    The labels are exactly the ``{별표구분}{번호}[의{가지번호}]`` composite that
    :func:`~..connectors.law_go_kr.annex_identity` builds and that an annex's ``canonical_key``
    carries after ``#``, so they join without a second naming scheme.

    Every observed value in the gated corpus carries **one** group whose date equals the parent's
    own 시행일자, so today this changes no value. It is read anyway because the alternative is for
    an annex's effective date to be an *inherited* value that happens to be right — and the day the
    authority stages an annex separately, an inherited date is silently wrong in the fourth element
    of the Citation tuple. Multiple groups are parsed even though none has been seen.
    """
    dates: dict[str, date] = {}
    for element in root.iter("별표시행일자문자열"):
        text = normalize_text(element.text or "")
        if not text:
            continue
        for group in _ANNEX_DATE_GROUP.split(text):
            match = _ANNEX_DATE_HEAD.match(group.strip())
            if not match:
                continue
            parsed = parse_authority_date(match.group(1))
            if parsed is None:
                continue
            for raw_label in match.group(2).split(","):
                # Whatever punctuation separates two date groups clings to the last label of the
                # previous one. The real separator is unobserved — every corpus value has a single
                # group — so strip the plausible ones rather than guessing which it is.
                label = normalize_text(raw_label).strip(",;/|·ㆍ ")
                if label:
                    dates[label] = parsed.date()
    return dates


def latest_addendum(root: Element) -> Element | None:
    """The last ``부칙단위`` — the one that applies to this version.

    ``부칙단위`` is a full history: 17 of them on 화장품법, back to 2011. Reading the first would
    describe an instrument superseded three times over.
    """
    units = list(root.iter("부칙단위"))
    return units[-1] if units else None


def enforcement_phrase(root: Element) -> str | None:
    """The 시행일 sentence of the newest 부칙, verbatim.

    This — not the eflaw list — is the record of staged application. For MST 282015 it carries five
    dates where the list returns three, and it preserves the conditions that make them meaningful:
    the same 개정규정 bites in 2028, 2030 or 2031 depending on the reader's annual revenue
    (ADR-0016). None of that is representable as a date, and none of it should be discarded.
    """
    unit = latest_addendum(root)
    if unit is None:
        return None
    body = normalize_text(unit.findtext("부칙내용") or "")
    if not body:
        return None

    if match := _ENFORCEMENT_ARTICLE.search(body):
        phrase = normalize_text(match.group("body"))
        if phrase:
            return _clip(phrase)

    if match := _BARE_ENFORCEMENT.search(body):
        return _clip(normalize_text(match.group(0)))

    return None


def clause_effective_date(raw: str | None, version_date: date | None) -> date | None:
    """``조문시행일자`` → a date, but **only where it differs from the version's**.

    Measured across all nine gated 법령 (ADR-0016): 조문시행일자 is constant within a document and
    always equals the document's own 시행일자. Writing it onto every clause would fill the column
    with a value that carries no information and make a genuine staged-application override
    indistinguishable from the default.

    The check stays because the override is real in EU instruments, and because the column belongs
    to the clause schema ADR-0002 warns is the most expensive thing to change later.
    """
    parsed = parse_authority_date(raw)
    if parsed is None:
        return None
    resolved = parsed.date()
    return None if resolved == version_date else resolved


def _clip(phrase: str, limit: int = 2000) -> str:
    """Keep the phrase readable. 부칙 제1조 runs long when application is staged by addressee."""
    return phrase if len(phrase) <= limit else phrase[: limit - 1] + "…"


__all__ = [
    "annex_effective_dates",
    "clause_effective_date",
    "enforcement_phrase",
    "envelope_effective_date",
    "latest_addendum",
]
