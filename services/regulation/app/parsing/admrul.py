"""행정규칙 profile — text mode over flat ``조문내용`` blobs.

**The 고시 envelope carries no clause structure at all.** Where 법령 본문조회 returns 조문단위 with
항/호/목 as elements, 행정규칙 본문조회 returns a flat sequence of ``조문내용`` strings — 화장품
안전기준 등에 관한 규정 comes back as 11 of them, one holding 제6조 and all of its 항/호 in 9,062
characters of text. Confirmed against the archive on 2026-08-06; ``조문형식여부`` is ``Y`` and there
is still no ``조문단위`` element.

So the same clause tree has to be recovered by segmentation rather than read off the envelope. That
is a **source-shape** branch — 법령 vs 고시 — and both gated cells have both kinds of source, which
is why it does not trip the phase 1.1 falsifier: nothing here is keyed on SaMD vs Cosmetic.

Annexes are *not* handled here. Each ``별표단위`` became its own child Document at ingestion
(ADR-0012) and is parsed by :mod:`.annex` against its own version.
"""

from __future__ import annotations

from xml.etree.ElementTree import Element

from regops_shared.constants import DriftSignal

from ..canonicalize import normalize_text
from .dates import enforcement_phrase, envelope_effective_date
from .model import ParsedDocument, ParseError
from .outline import segment_outline

PROFILE = "admrul_text"

#: This profile takes a parsed XML root, not the archived bytes. See :mod:`.` .
ACCEPTS_RAW = False


def parse(root: Element) -> ParsedDocument:
    """Parse a 행정규칙 본문조회 envelope into a clause tree."""
    document = ParsedDocument(
        profile=PROFILE,
        effective_date=envelope_effective_date(root),
        effective_date_phrase=enforcement_phrase(root),
    )

    body = _body_text(root)
    if not body.strip():
        raise ParseError(
            "행정규칙 response carried no 조문내용 outside its annexes",
            signal=DriftSignal.ZERO_CLAUSES,
            expected="at least one non-empty 조문내용",
        )

    document.clauses = segment_outline(body)
    if not document.clauses:
        raise ParseError(
            "행정규칙 body matched no clause marker — 제N조 / 항 / 호 numbering is absent, so the "
            "text cannot be addressed and nothing here is citable",
            signal=DriftSignal.ZERO_CLAUSES,
            expected="제N조 … numbering in 조문내용",
        )
    return document


def _body_text(root: Element) -> str:
    """Every ``조문내용`` outside a ``별표단위``, joined in document order.

    The exclusion matters: an annex's own content is reached through ``별표내용``, but some
    envelopes repeat body-like text inside the annex subtree, and absorbing it here would duplicate
    clauses into the parent document under paths the annex already owns.
    """
    annexed = {id(element) for unit in root.iter("별표단위") for element in unit.iter("조문내용")}
    blobs = [
        normalize_text(element.text or "")
        for element in root.iter("조문내용")
        if id(element) not in annexed
    ]
    return "\n".join(blob for blob in blobs if blob)


__all__ = ["PROFILE", "parse"]
