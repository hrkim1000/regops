"""Hybrid retrieval — deterministic, and the half of this layer that decides what can be cited.

A pipeline, not an agent: no model judges anything here. What it returns is the *entire* universe
generation is allowed to cite (ADR-0006 decision 4), which is why it runs before any prompt is built
and why its output is recorded on the answer.

Three arms, split by what the query keys on (decision 3):

| Query shape | Arm |
|---|---|
| 원료명, CAS No., 조문 번호, 고시 번호 | lexical/exact — ``65-29-2`` has no useful embedding |
| "언제까지 신고해야 하나", "안전성 평가 의무가 있나" | vector — paraphrase-tolerant |
| "화장품법 제8조" | identifier — direct clause resolution, not a ranked guess |

The 별표 finding makes this concrete rather than theoretical: regulatory corpora are unusually
identifier-dense, so a vector-only design underperforms badly on exactly the questions RA staff ask
most. Results are fused by reciprocal rank, with exact matches placed above the fused set — an
identifier the user named outright is not a candidate to be ranked, it is the answer to *where*.

Scope is enforced here and nowhere else: **cell**, so a cosmetic question is never answered from
device regulation (decision 9), and **version**, so an answer names the versions it was drawn from
rather than implying "current" (decision 8).
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import date

import structlog

from regops_shared.constants import (
    RETRIEVAL_CANDIDATES,
    RETRIEVAL_IDENTIFIER_BOOST,
    RETRIEVAL_LEXICAL_WEIGHT,
    RETRIEVAL_TOP_K,
    RETRIEVAL_VECTOR_WEIGHT,
    RRF_K,
)
from regops_shared.llm import LLMClient

from .embedding import embed_text
from .store import (
    Hit,
    VersionRef,
    annex_row_lookup,
    identifier_lookup,
    lexical_search,
    vector_search,
)

log = structlog.get_logger(__name__)

#: 제8조, 제8조의2, 제3항, 제1호 — the address forms `clauses.path_segments` actually holds.
#: The branch suffix follows the unit, not the number: 제8조의2 is 제 + 8 + 조 + 의2, and a pattern
#: that looked for 의N before the unit would silently read it as 제8조 — a different article.
_KO_IDENTIFIER = re.compile(r"제\s*(\d+)\s*(조|항|호|목|장|절|편|관)\s*(의\s*\d+)?")
#: 별표 1, 별표1의2, 별지 3 — annex and form addresses.
_KO_ANNEX = re.compile(r"(별표|별지|서식)\s*(\d+(?:의\s*\d+)?)")
#: § 892.2050 — the US form, kept because the EU/FDA spike shares this retrieval path.
_EN_IDENTIFIER = re.compile(r"§\s*(\d+(?:\.\d+)*)")
#: A CAS registry number. The single most identifier-like thing in the cosmetic corpus.
_CAS = re.compile(r"\b\d{2,7}-\d{2}-\d\b")

_WORD = re.compile(r"[^\w가-힣ㄱ-ㆎ.\-]+", re.UNICODE)
#: Below this a token is too generic to key an annex row on. Measured against the corpus rather than
#: guessed: 화장품, 안전성 and 평가 are all three characters and all match column values across
#: 별표 1 and 별표 2, which turned an ingredient lookup into a list of unrelated table rows. Real
#: 원료명 run far longer — 갈라민트리에치오다이드 is eleven — so the floor costs nothing real.
_MIN_ANNEX_TERM_LEN = 5


@dataclass(slots=True)
class RetrievalResult:
    """What retrieval found, and the scope it was bound to.

    ``versions`` and ``effective_date_scope`` are not diagnostics — they are what the answer must
    state (decision 8), and ``straddles_effective_date`` is the case the answer must call out rather
    than resolve silently.
    """

    hits: list[Hit] = field(default_factory=list)
    versions: list[VersionRef] = field(default_factory=list)
    identifiers: tuple[str, ...] = ()
    annex_terms: tuple[str, ...] = ()
    effective_date_scope: date | None = None
    straddles_effective_date: bool = False

    @property
    def empty(self) -> bool:
        return not self.hits

    def citable_paths(self) -> set[tuple[uuid.UUID, str]]:
        """Every ``(version, clause_path)`` generation is permitted to cite.

        A retrieved 조 licenses its 항/호/목 too — that is decision 1's split granularity, and it is
        why this is a *set of paths* rather than the list of hits. A citation outside this set is
        fabricated by definition, and decision 4 rejects it mechanically.
        """
        allowed: set[tuple[uuid.UUID, str]] = set()
        for hit in self.hits:
            allowed.add((hit.document_version_id, hit.clause_path))
            for path in hit.child_clause_paths:
                allowed.add((hit.document_version_id, path))
        return allowed


def retrieve(
    session,
    *,
    query: str,
    versions: list[VersionRef],
    client: LLMClient,
    top_k: int = RETRIEVAL_TOP_K,
    today: date | None = None,
) -> RetrievalResult:
    """Run every arm over the pinned versions and fuse the results."""
    result = RetrievalResult(versions=versions)
    version_ids = [version.version_id for version in versions]
    if not version_ids:
        return result

    result.identifiers = extract_identifiers(query)
    result.annex_terms = extract_annex_terms(query)

    exact: list[Hit] = identifier_lookup(
        session,
        identifiers=list(result.identifiers),
        version_ids=version_ids,
        limit=RETRIEVAL_CANDIDATES,
    )
    rows: list[Hit] = annex_row_lookup(
        session,
        terms=list(result.annex_terms),
        version_ids=version_ids,
        limit=RETRIEVAL_CANDIDATES,
    )
    lexical = lexical_search(
        session, query=query, version_ids=version_ids, limit=RETRIEVAL_CANDIDATES
    )
    vector = vector_search(
        session,
        embedding=embed_text(client, query),
        version_ids=version_ids,
        limit=RETRIEVAL_CANDIDATES,
    )

    result.hits = fuse(exact=exact, rows=rows, lexical=lexical, vector=vector, top_k=top_k)
    _scope_dates(result, today=today or date.today())

    log.info(
        "retrieve.done",
        identifiers=list(result.identifiers),
        exact=len(exact),
        annex_rows=len(rows),
        lexical=len(lexical),
        vector=len(vector),
        kept=len(result.hits),
        straddles=result.straddles_effective_date,
    )
    return result


def fuse(
    *,
    exact: list[Hit],
    rows: list[Hit],
    lexical: list[Hit],
    vector: list[Hit],
    top_k: int,
) -> list[Hit]:
    """Reciprocal-rank fusion, with exact matches lifted above the fused set.

    RRF rather than score normalisation: ``ts_rank_cd`` and cosine similarity are not on the same
    scale and never will be, so combining the raw numbers would silently let whichever arm happens
    to produce larger values dominate. Rank is the only thing the two arms agree on.

    Exact matches — an identifier the query named, or an annex row whose column *equals* a term —
    are not ranked candidates. *"화장품법 제8조"* has one right answer, and an acceptance criterion
    says it comes back at rank 1.
    """
    scores: dict[tuple[uuid.UUID, str], float] = {}
    best: dict[tuple[uuid.UUID, str], Hit] = {}

    def contribute(hits: list[Hit], weight: float) -> None:
        for rank, hit in enumerate(hits):
            key = (hit.document_version_id, hit.clause_path)
            scores[key] = scores.get(key, 0.0) + weight / (RRF_K + rank + 1)
            # Keep the richest copy: only the vector arm carries child_clause_paths and the stored
            # passage. Losing the paths would narrow what generation is allowed to cite; losing the
            # passage would send the raw clause text to the model instead of the bounded unit the
            # vector actually matched.
            previous = best.get(key)
            if previous is None or (
                (not previous.child_clause_paths and hit.child_clause_paths)
                or (previous.passage is None and hit.passage is not None)
            ):
                best[key] = hit

    contribute(lexical, RETRIEVAL_LEXICAL_WEIGHT)
    contribute(vector, RETRIEVAL_VECTOR_WEIGHT)
    contribute(rows, RETRIEVAL_LEXICAL_WEIGHT)
    contribute(exact, RETRIEVAL_LEXICAL_WEIGHT)

    for hit in (*exact, *(row for row in rows if row.score >= 1.0)):
        key = (hit.document_version_id, hit.clause_path)
        scores[key] = scores.get(key, 0.0) + RETRIEVAL_IDENTIFIER_BOOST
        best.setdefault(key, hit)

    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0][1]))
    return [
        Hit(
            clause_id=best[key].clause_id,
            clause_path=best[key].clause_path,
            document_version_id=best[key].document_version_id,
            heading=best[key].heading,
            text=best[key].text,
            kind=best[key].kind,
            effective_date=best[key].effective_date,
            score=score,
            child_clause_paths=best[key].child_clause_paths,
            passage=best[key].passage,
        )
        for key, score in ordered[:top_k]
    ]


def _scope_dates(result: RetrievalResult, *, today: date) -> None:
    """Work out what date the answer is "as of", and whether the evidence straddles a boundary.

    The live API returns 조문시행일자 per clause, so a document routinely holds provisions in force
    beside provisions amended-but-not-yet-effective. An answer that silently mixes them is wrong in
    the way that costs a customer an approval, so the straddle is recorded and said out loud rather
    than resolved by picking one.
    """
    dates = [hit.effective_date for hit in result.hits if hit.effective_date is not None]
    in_force = [value for value in dates if value <= today]
    pending = [value for value in dates if value > today]

    result.effective_date_scope = max(in_force) if in_force else (min(pending) if pending else None)
    result.straddles_effective_date = bool(in_force) and bool(pending)


# --- query parsing ---------------------------------------------------------------------------


def extract_identifiers(query: str) -> tuple[str, ...]:
    """Clause addresses the query names outright, normalised to stored path segments.

    Whitespace inside 제 8 조 is dropped: a user types it and the store does not. 제8조의2 keeps
    its 의2: it is a different article from 제8조, and collapsing them would answer a question about
    one with the text of the other.
    """
    found: list[str] = []
    for number, unit, branch in _KO_IDENTIFIER.findall(query or ""):
        found.append(f"제{number}{unit}{branch.replace(' ', '')}")
    for kind, number in _KO_ANNEX.findall(query or ""):
        found.append(f"{kind}{number.replace(' ', '')}")
    for number in _EN_IDENTIFIER.findall(query or ""):
        found.append(f"§ {number}")
    return tuple(dict.fromkeys(found))


def extract_annex_terms(query: str) -> tuple[str, ...]:
    """Values that could name a row in an annex table's identifier column.

    CAS numbers first, because they are unambiguous. Then the long tokens — an ingredient name is
    typically one long token, and the length floor keeps particles and function words from
    prefix-matching half the 원료 list.

    Korean particles are stripped as well as matched: a user types 갈라민트리에치오다이드**는**, and
    the column holds the bare name. The store also matches the other direction, so both the typed
    form and its stem get a chance rather than the question failing on a grammatical suffix.
    """
    text_value = query or ""
    terms: list[str] = list(_CAS.findall(text_value))
    for raw in _WORD.split(text_value):
        token = raw.strip()
        if len(token) < _MIN_ANNEX_TERM_LEN or token.isdigit():
            continue
        terms.append(token)
        if _is_hangul(token[-1]):
            terms.append(token[:-1])
        if len(token) > _MIN_ANNEX_TERM_LEN + 1 and _is_hangul(token[-1]):
            terms.append(token[:-2])
    return tuple(term for term in dict.fromkeys(terms) if len(term) >= _MIN_ANNEX_TERM_LEN)


def _is_hangul(char: str) -> bool:
    return "가" <= char <= "힣"


__all__ = [
    "RetrievalResult",
    "extract_annex_terms",
    "extract_identifiers",
    "fuse",
    "retrieve",
]
