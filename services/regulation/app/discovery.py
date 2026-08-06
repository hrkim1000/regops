"""Source discovery — reconcile the curated catalog against the authority's own list.

`import-source-map.md` stays the registry of what we *intend* to cover, but a hand-maintained list
silently caps detection coverage at whatever someone remembered to add. The 행정규칙 목록 API
enumerates every MFDS 고시 by 소관부처, so the gap is measurable rather than unknown
(ADR-0003 decision 11).

Three things about this module are deliberate.

**It never archives.** The 목록 endpoint echoes the ``OC`` parameter straight back inside every row
(``행정규칙상세링크`` is a fully-formed URL containing the key). These responses are consumed in
memory and discarded; :func:`regops_shared.storage.archive_bytes` would refuse them anyway.

**:class:`UpstreamRule` has no link field.** Same reasoning as ``fetch_observations`` having no
request-URL column: ``source_discovery_runs.details`` is persisted JSON, so the safe design is one
where the credential-bearing value is never carried far enough to be written.

**The relevance filter is over-inclusive.** 511 MFDS 고시 are mostly 식품 and 건강기능식품, which
belong to no RegOps cell; alerting on all of them would be 500 false positives and the sweep would
be muted within a week. Filtering to the cell keywords produces a list a human can actually triage —
and the unfiltered total is recorded alongside it, so the narrowing is visible rather than silent.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime

import structlog
from defusedxml.ElementTree import fromstring as parse_xml
from sqlalchemy import select
from sqlalchemy.orm import Session

from regops_shared.constants import (
    DISCOVERY_EXCLUSIONS,
    DISCOVERY_KEYWORDS,
    MFDS_ORG_CODE,
    Authority,
)
from regops_shared.models import Cell, Document, DocumentCell, Source, SourceDiscoveryRun
from regops_shared.models.base import utcnow
from regops_shared.settings import get_settings

from .connectors.http import PoliteFetcher, resolve_url

log = structlog.get_logger(__name__)

ADMRUL_INDEX = (
    "https://www.law.go.kr/DRF/lawSearch.do?OC={OC}&target=admrul&org={org}"
    "&type=XML&display={display}&page={page}"
)

#: The authority caps a page at 100 rows.
PAGE_SIZE = 100

#: Backstop against an unbounded walk if the authority's totalCnt is wrong. 20 pages is 2000 rows
#: against an observed 511 — generous, and a truncated sweep is logged rather than passed off as
#: complete.
MAX_PAGES = 20


@dataclass(frozen=True, slots=True)
class UpstreamRule:
    """One row of the authority's own list.

    No link field, on purpose — see the module docstring.
    """

    admrul_id: str
    title: str
    kind: str | None = None
    promulgated_on: str | None = None
    effective_on: str | None = None
    revision_kind: str | None = None

    def as_details(self) -> dict[str, str | None]:
        return {
            "admrul_id": self.admrul_id,
            "title": self.title,
            "kind": self.kind,
            "promulgated_on": self.promulgated_on,
            "revision_kind": self.revision_kind,
        }


def normalize_title(value: str) -> str:
    """Compare titles the way a reader would — case, spacing and 중점 vary between the catalog and
    the authority's own spelling without naming a different instrument."""
    folded = unicodedata.normalize("NFC", value).strip().lower()
    for ch in (" ", "·", "·", "ㆍ", "・", "‧"):
        folded = folded.replace(ch, "")
    return folded


def excluded_by(title: str) -> str | None:
    """The exclusion term that puts this title out of scope, or ``None``.

    Separate from :func:`cells_for` so the triage report can say *which* decision removed a row.
    "Seen and rejected" and "never seen" are different states, and only the first is revisitable.
    """
    normalized = unicodedata.normalize("NFC", title)
    return next((term for term in DISCOVERY_EXCLUSIONS if term in normalized), None)


def keyword_cells(title: str) -> frozenset[str]:
    """Cells matched by the positive keywords alone, **ignoring exclusions**.

    Only reporting needs this. It is what distinguishes "we saw this and ruled it out" from "this
    was never in scope to begin with" — 국가연구개발성과 범부처 이어달리기 프로젝트 contains
    범부처 but names no product domain, so calling it *excluded* credits a decision nobody made.
    """
    normalized = unicodedata.normalize("NFC", title)
    return frozenset(
        cell
        for cell, keywords in DISCOVERY_KEYWORDS.items()
        if any(keyword in normalized for keyword in keywords)
    )


def cells_for(title: str) -> frozenset[str]:
    """Which cells a title plausibly belongs to. Empty means out of RegOps scope.

    **Exclusion beats inclusion.** The keywords are substrings, so 체외진단의료기기 matches 의료기기
    however the positive list is written — a negative list is the only thing that can remove it
    (``DISCOVERY_EXCLUSIONS``).
    """
    return frozenset() if excluded_by(title) else keyword_cells(title)


def _text(element, tag: str) -> str | None:
    found = element.find(tag)
    if found is None or not found.text:
        return None
    return found.text.strip() or None


def fetch_admrul_index(
    *,
    org: str = MFDS_ORG_CODE,
    fetcher: PoliteFetcher | None = None,
    max_pages: int = MAX_PAGES,
) -> tuple[list[UpstreamRule], bool]:
    """Walk the authority's 행정규칙 list. Returns ``(rules, truncated)``."""
    owned = fetcher is None
    client = fetcher or PoliteFetcher()
    rules: list[UpstreamRule] = []
    truncated = False
    try:
        for page in range(1, max_pages + 1):
            # Fill everything except the credential, then resolve that separately so the key is
            # substituted in exactly one place and never lands in a local we might log.
            template = ADMRUL_INDEX.format(OC="{OC}", org=org, display=PAGE_SIZE, page=page)
            url = resolve_url(template, credential=get_settings().law_go_kr_oc)
            response = client.get(url)
            if response.status != 200:
                raise RuntimeError(f"admrul index page {page}: HTTP {response.status}")

            page_rules = list(parse_index(response.body))
            rules.extend(page_rules)
            if len(page_rules) < PAGE_SIZE:
                break
        else:
            truncated = True
    finally:
        if owned:
            client.close()

    if truncated:
        # Never let a bounded walk read as complete coverage.
        log.warning("discovery.truncated", pages=max_pages, collected=len(rules))
    return rules, truncated


def parse_index(body: bytes) -> Iterator[UpstreamRule]:
    root = parse_xml(body)
    for item in root.iter("admrul"):
        title = _text(item, "행정규칙명")
        admrul_id = _text(item, "행정규칙ID") or _text(item, "행정규칙일련번호")
        if not title or not admrul_id:
            continue
        yield UpstreamRule(
            admrul_id=admrul_id,
            title=title,
            kind=_text(item, "행정규칙종류"),
            promulgated_on=_text(item, "발령일자"),
            effective_on=_text(item, "시행일자"),
            revision_kind=_text(item, "제개정구분명"),
        )


def known_titles(session: Session, *, authority: Authority = Authority.MFDS) -> set[str]:
    """What we already cover — ingested documents first, seeded source titles as the fallback.

    Document titles come from the API response itself, so they are the authority's own spelling and
    match exactly. Source titles come from the catalog and may differ slightly; including both is
    what keeps a spelling difference from reading as a coverage gap.
    """
    cell_ids = [
        cell.id for cell in session.scalars(select(Cell).where(Cell.authority == authority))
    ]
    documents = session.scalars(
        select(Document)
        .join(DocumentCell, DocumentCell.document_id == Document.id)
        .where(DocumentCell.cell_id.in_(cell_ids))
    )
    sources = session.scalars(select(Source).where(Source.cell_id.in_(cell_ids)))
    return {normalize_title(d.title) for d in documents} | {
        normalize_title(s.title) for s in sources
    }


def reconcile(
    session: Session,
    rules: list[UpstreamRule],
    *,
    authority: Authority = Authority.MFDS,
    truncated: bool = False,
    ran_at: datetime | None = None,
) -> SourceDiscoveryRun:
    """Record the delta. Writes one ``source_discovery_runs`` row; the caller commits."""
    known = known_titles(session, authority=authority)

    in_scope = [rule for rule in rules if cells_for(rule.title)]
    unmatched = [rule for rule in in_scope if normalize_title(rule.title) not in known]

    run = SourceDiscoveryRun(
        authority=authority,
        ran_at=ran_at or utcnow(),
        # The authority's full count, not the filtered one: a sweep that reported only what it
        # chose to look at would make its own narrowing invisible.
        upstream_count=len(rules),
        matched=len(in_scope) - len(unmatched),
        unmatched=len(unmatched),
        details={
            "in_scope_count": len(in_scope),
            "truncated": truncated,
            "keywords": {cell: list(words) for cell, words in DISCOVERY_KEYWORDS.items()},
            "unmatched": [
                {**rule.as_details(), "cells": sorted(cells_for(rule.title))} for rule in unmatched
            ],
        },
    )
    session.add(run)
    session.flush()
    log.info(
        "discovery.reconciled",
        upstream=len(rules),
        in_scope=len(in_scope),
        unmatched=len(unmatched),
        truncated=truncated,
    )
    return run


__all__ = [
    "ADMRUL_INDEX",
    "MAX_PAGES",
    "PAGE_SIZE",
    "UpstreamRule",
    "cells_for",
    "fetch_admrul_index",
    "known_titles",
    "normalize_title",
    "parse_index",
    "reconcile",
]
