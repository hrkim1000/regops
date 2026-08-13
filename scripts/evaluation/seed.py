"""Seeding a golden set: what a template can honestly write, and what it cannot.

Three axes are generated here, and three are not, on one criterion — whether a template produces a
*faithful* instance of the axis or merely a plausible-looking one.

Generated, because the template is the axis:

``identifier``
    "「화장품법」 제5조는 무엇을 규정하고 있습니까?" *is* an identifier lookup. There is no
    judgement in it, and generating forty of them from the clause store gives the axis a real
    denominator rather than a token one.

``mis_citation``
    A trap is only a trap if the clause it names provably does not exist, or provably says
    something else. Both are database facts, so generating these is *more* reliable than writing
    them by hand — a hand-written trap can accidentally name a real clause.

``cross_domain``
    A genuine cosmetic question asked in the device cell. The question has to be a real obligation
    from the neighbouring cell, which is exactly what the neighbouring cell's clause store holds.

Hand-authored, in ``<cell>.curated.json``, because a template cannot write them:

``conceptual``
    A paraphrase that reuses the statute's own vocabulary is an identifier lookup wearing a
    sentence. Only a person who has read the clause can ask it in a reader's words.

``effective_date``
    Requires knowing which two versions of a provision differ and what turns on the difference.

``unanswerable``
    Requires knowing what the corpus does *not* contain, which no query over the corpus can tell
    you.

Seeding proposes; it never signs. The output carries ``ra_signed_off: false``, and
:func:`~scripts.evaluation.goldenset.validate_composition` reports that a run over an unsigned set
measures the harness rather than the product.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from regops_shared.constants import Domain, EvaluationAxis, ExpectedOutcome

from . import corpus
from .goldenset import GoldenItem, GoldenSet, article_of, load

#: How many of each generated axis. Enough that a per-axis score has a real denominator rather
#: than a token one; the hard axes are hand-authored and counted separately.
TARGETS = {
    EvaluationAxis.IDENTIFIER: 40,
    EvaluationAxis.MIS_CITATION: 30,
    EvaluationAxis.CROSS_DOMAIN: 30,
}

#: Rotated so the set does not measure one phrasing. Not paraphrase — these are all identifier
#: lookups, and pretending otherwise is what the conceptual axis exists to prevent.
IDENTIFIER_TEMPLATES = (
    "「{title}」 {article}은(는) 무엇을 규정하고 있습니까?",
    "「{title}」 {article}({heading})의 내용을 알려주세요.",
    "「{title}」 {article}에 규정된 사항은 무엇입니까?",
    "{heading}에 관한 「{title}」 {article}의 규정 내용은?",
)

MISSING_TEMPLATES = (
    "「{title}」 {article}에 따른 제출 의무는 무엇입니까?",
    "「{title}」 {article}이(가) 정하는 기준을 알려주세요.",
)

DELETED_TEMPLATE = "「{title}」 {article}은(는) 어떤 의무를 정하고 있습니까?"

CROSS_DOMAIN_TEMPLATE = "「{title}」 {article}({heading})에 따른 의무는 무엇입니까?"

_ARTICLE_NUMBER = re.compile(r"^제(\d+)조")


@dataclass(frozen=True, slots=True)
class Article:
    document: str
    version_id: str
    clause_path: str
    article: str
    heading: str | None
    ordinal: int

    @property
    def number(self) -> int:
        match = _ARTICLE_NUMBER.match(self.article)
        return int(match.group(1)) if match else 0

    @property
    def usable(self) -> bool:
        """A 삭제 clause has no content to ask about — trap material, not lookup material."""
        return bool(self.heading) and "삭제" not in (self.heading or "")


def read_articles(session: Session, cell_id) -> list[Article]:
    """Every 조 of every in-force instrument in the cell, in document order.

    In-force only. A golden item pinned to a not-yet-effective version would be answered correctly
    and scored wrong the day it comes into force, and the effective-date axis covers that case
    deliberately rather than by accident.
    """
    out: list[Article] = []
    for title, version in corpus.in_force_versions(session, cell_id).items():
        for ordinal, (path, heading) in enumerate(corpus.articles(session, version.id)):
            out.append(
                Article(
                    document=title,
                    version_id=str(version.id),
                    clause_path=path,
                    article=article_of(path),
                    heading=heading,
                    ordinal=ordinal,
                )
            )
    return out


def _spread(articles: Sequence[Article], count: int) -> list[Article]:
    """Take ``count`` articles spread across instruments rather than the first N of the biggest.

    Round-robin by document. Taking a contiguous block would make the identifier axis a test of one
    instrument's parse quality, which is not what it is for.
    """
    by_document: dict[str, list[Article]] = {}
    for article in articles:
        by_document.setdefault(article.document, []).append(article)
    picked: list[Article] = []
    index = 0
    while len(picked) < count and any(len(rows) > index for rows in by_document.values()):
        for document in sorted(by_document):
            rows = by_document[document]
            if index < len(rows) and len(picked) < count:
                picked.append(rows[index])
        index += 1
    return picked


def generate_identifier(prefix: str, articles: Sequence[Article]) -> list[GoldenItem]:
    usable = [article for article in articles if article.usable]
    items: list[GoldenItem] = []
    for index, article in enumerate(_spread(usable, TARGETS[EvaluationAxis.IDENTIFIER])):
        template = IDENTIFIER_TEMPLATES[index % len(IDENTIFIER_TEMPLATES)]
        items.append(
            GoldenItem(
                id=f"{prefix}-ident-{index + 1:03d}",
                axis=EvaluationAxis.IDENTIFIER,
                question=template.format(
                    title=article.document, article=article.article, heading=article.heading
                ),
                expected_outcome=ExpectedOutcome.ANSWERED,
                expected_document=article.document,
                expected_clause_paths=(article.clause_path,),
                expected_answer=f"{article.heading}에 관한 규정",
                notes="Identifier lookup: must resolve exactly, not fuzzily.",
            )
        )
    return items


def generate_mis_citation(prefix: str, articles: Sequence[Article]) -> list[GoldenItem]:
    """Two families, both grounded in what the store does and does not hold.

    **Non-existent article.** The number is chosen past the last 조 the instrument actually has, so
    "does this clause exist" is a fact rather than an opinion. Refusing is correct; answering is a
    confident answer about a provision that was never enacted.

    **Deleted article.** 화장품법 제21조 is ``삭제 <2013.7.30>``. The path exists and holds no
    obligation, and the failure mode is answering from the *neighbouring* articles — so those are
    the forbidden paths. This is the trap the mechanical citation check cannot catch on its own: a
    citation to 제20조 resolves perfectly well and is still the wrong clause.
    """
    items: list[GoldenItem] = []
    by_document: dict[str, list[Article]] = {}
    for article in articles:
        by_document.setdefault(article.document, []).append(article)

    index = 0
    for document in sorted(by_document):
        rows = by_document[document]
        highest = max((row.number for row in rows), default=0)
        if highest < 5:
            continue
        for offset in (11, 27):
            index += 1
            if index > TARGETS[EvaluationAxis.MIS_CITATION]:
                break
            fake = f"제{highest + offset}조"
            items.append(
                GoldenItem(
                    id=f"{prefix}-mis-{index:03d}",
                    axis=EvaluationAxis.MIS_CITATION,
                    question=MISSING_TEMPLATES[index % len(MISSING_TEMPLATES)].format(
                        title=document, article=fake
                    ),
                    expected_outcome=ExpectedOutcome.NEEDS_VERIFICATION,
                    expected_document=document,
                    forbidden_clause_paths=(fake,),
                    expected_answer="확인 필요 — 해당 조문이 존재하지 않음",
                    notes=(
                        f"{document} ends at 제{highest}조; {fake} was never enacted. Answering "
                        f"confirms a premise that is false."
                    ),
                )
            )

    for document in sorted(by_document):
        rows = by_document[document]
        for position, article in enumerate(rows):
            if index >= TARGETS[EvaluationAxis.MIS_CITATION]:
                break
            if article.usable:
                continue
            neighbours = [
                rows[offset].clause_path
                for offset in (position - 1, position + 1)
                if 0 <= offset < len(rows) and rows[offset].usable
            ]
            if not neighbours:
                continue
            index += 1
            items.append(
                GoldenItem(
                    id=f"{prefix}-mis-{index:03d}",
                    axis=EvaluationAxis.MIS_CITATION,
                    question=DELETED_TEMPLATE.format(title=document, article=article.article),
                    expected_outcome=ExpectedOutcome.NEEDS_VERIFICATION,
                    expected_document=document,
                    forbidden_clause_paths=tuple(neighbours),
                    expected_answer="확인 필요 — 삭제된 조문",
                    notes=(
                        "Deleted article. The failure mode is answering from the neighbouring "
                        "articles, whose citations resolve perfectly well and are still wrong."
                    ),
                )
            )
    return items


def generate_cross_domain(
    prefix: str, neighbour_articles: Sequence[Article], neighbour_cell: str
) -> list[GoldenItem]:
    """Real obligations from the neighbouring cell, asked here with cross-cell off.

    The correct behaviour is to decline. Answering a cosmetic question out of device regulation is
    a *confident* wrong answer, which is the one failure mode worse than an empty one.
    """
    usable = [article for article in neighbour_articles if article.usable]
    items: list[GoldenItem] = []
    for index, article in enumerate(_spread(usable, TARGETS[EvaluationAxis.CROSS_DOMAIN])):
        items.append(
            GoldenItem(
                id=f"{prefix}-cross-{index + 1:03d}",
                axis=EvaluationAxis.CROSS_DOMAIN,
                question=CROSS_DOMAIN_TEMPLATE.format(
                    title=article.document, article=article.article, heading=article.heading
                ),
                expected_outcome=ExpectedOutcome.NEEDS_VERIFICATION,
                expected_document=None,
                cross_cell=False,
                expected_answer="확인 필요 — 이 셀의 규정이 아님",
                notes=f"Belongs to {neighbour_cell}. Declining is correct (ADR-0006 decision 9).",
            )
        )
    return items


def build(
    session: Session,
    *,
    cell: str,
    neighbour_cell: str,
    curated_path: Path,
    set_version: str,
) -> GoldenSet:
    """Generated axes plus the curated file, in one set.

    The curated file is the source of truth for the axes it covers: a re-seed regenerates the
    templated items and leaves hand-authored ones exactly as written.
    """
    registry = corpus.cells(session)
    if cell not in registry or neighbour_cell not in registry:
        raise SystemExit(f"unknown cell: {cell} / {neighbour_cell}")

    prefix = "samd" if registry[cell].domain == Domain.SAMD.value else "cos"
    articles = read_articles(session, registry[cell].id)
    neighbour = read_articles(session, registry[neighbour_cell].id)

    items = [
        *generate_identifier(prefix, articles),
        *generate_mis_citation(prefix, articles),
        *generate_cross_domain(prefix, neighbour, neighbour_cell),
    ]
    if curated_path.exists():
        items.extend(load(curated_path).items)

    return GoldenSet(
        cell=cell,
        domain=Domain(registry[cell].domain),
        set_version=set_version,
        items=tuple(sorted(items, key=lambda item: item.id)),
        authored_at=datetime.now(UTC).date(),
        ra_signed_off=False,
        notes=(
            "Seeded, not signed. Identifier, mis-citation and cross-domain items are generated "
            "from the clause store; conceptual, effective-date and unanswerable items are "
            "hand-authored in the .curated.json beside this file. No run over this set may be "
            "quoted against a Go/No-Go gate until an RA reviews every item and sets "
            "ra_signed_off."
        ),
    )


def today() -> date:
    return datetime.now(UTC).date()


__all__ = [
    "TARGETS",
    "Article",
    "build",
    "generate_cross_domain",
    "generate_identifier",
    "generate_mis_citation",
    "read_articles",
]
