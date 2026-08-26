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

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Final

from sqlalchemy.orm import Session

from regops_shared.constants import Domain, EvaluationAxis, ExpectedOutcome

from . import corpus
from . import phrasing as phrasing_module
from .goldenset import GoldenItem, GoldenSet, article_of, load
from .phrasing import Phrasing

#: How many of each generated axis. Enough that a per-axis score has a real denominator rather
#: than a token one; the hard axes are hand-authored and counted separately.
TARGETS = {
    EvaluationAxis.IDENTIFIER: 40,
    EvaluationAxis.MIS_CITATION: 30,
    EvaluationAxis.CROSS_DOMAIN: 30,
}

#: How far past an instrument's last provision a fabricated identifier is placed. Several, because
#: the axis is filled per *document* and a cell with few instruments would otherwise come up short —
#: `fda_cosmetic` holds four CFR Parts and reached 17 of 30 on a pair of offsets. Every one of them
#: is past the end, so each is as provably absent as the first; what varies is only how far.
_ABSENT_OFFSETS: Final[tuple[int, ...]] = (11, 27, 43, 59, 71, 87)


@dataclass(frozen=True, slots=True)
class Article:
    document: str
    version_id: str
    clause_path: str
    article: str
    heading: str | None
    ordinal: int
    #: How this instrument is numbered and worded (:mod:`.phrasing`), from its version's language.
    phrasing: Phrasing = phrasing_module.KOREAN

    @property
    def number(self) -> int:
        return self.phrasing.number_of(self.article)

    @property
    def usable(self) -> bool:
        """A 삭제 or ``[Reserved]`` clause has no content to ask about — trap, not lookup."""
        return not self.phrasing.vacant(self.heading)


def read_articles(session: Session, cell_id) -> list[Article]:
    """Every 조 of every in-force instrument in the cell, in document order.

    In-force only. A golden item pinned to a not-yet-effective version would be answered correctly
    and scored wrong the day it comes into force, and the effective-date axis covers that case
    deliberately rather than by accident.
    """
    out: list[Article] = []
    for title, version in corpus.in_force_versions(session, cell_id).items():
        phrasing = phrasing_module.for_language(version.language)
        rows = corpus.articles(session, version.id, article_pattern=phrasing.article_pattern)
        for ordinal, (path, heading) in enumerate(rows):
            out.append(
                Article(
                    document=title,
                    version_id=str(version.id),
                    clause_path=path,
                    article=article_of(path),
                    heading=heading,
                    ordinal=ordinal,
                    phrasing=phrasing,
                )
            )
    return out


def _spread(articles: Sequence[Article], count: int) -> list[Article]:
    """Take ``count`` articles spread across instruments rather than the first N of the biggest.

    Round-robin by document. Taking a contiguous block would make the identifier axis a test of one
    instrument's parse quality, which is not what it is for.

    **Known defect, recorded 2026-08-26 and not fixed here** — phase1.6 *Deviations* 15.
    The round-robin takes index 0 from every document, then index 1, and so on — so when there are
    more documents in scope than the target count, **it stops after index 0**. `mfds_samd` has 40+
    instruments and a target of 40, so all 40 identifier items ask about **제1조**: the axis samples
    *article 1 of 40 documents* rather than 40 varied citations, and 제1조 is the 목적 clause that
    extraction excludes as `scope`.

    Document diversity was the goal and was achieved; article diversity was lost in the same move,
    and both read as "spread". The fix is to spread across position as well as document — it changes
    the **gated** MFDS sets, so it carries a re-score.
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
        phrasing = article.phrasing
        template = phrasing.identifier_templates[index % len(phrasing.identifier_templates)]
        items.append(
            GoldenItem(
                id=f"{prefix}-ident-{index + 1:03d}",
                axis=EvaluationAxis.IDENTIFIER,
                question=template.format(
                    title=article.document,
                    article=article.article,
                    heading=phrasing.display_heading(article.heading),
                ),
                expected_outcome=ExpectedOutcome.ANSWERED,
                expected_document=article.document,
                expected_clause_paths=(article.clause_path,),
                expected_answer=phrasing.answer_for(
                    phrasing.display_heading(article.heading) or article.article
                ),
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
        phrasing = rows[0].phrasing
        highest_row = max(rows, key=lambda row: row.number, default=None)
        if highest_row is None or highest_row.number < 5:
            continue
        highest = highest_row.number
        for offset in _ABSENT_OFFSETS:
            index += 1
            if index > TARGETS[EvaluationAxis.MIS_CITATION]:
                break
            fake = phrasing.absent_article(highest_row.article, offset)
            items.append(
                GoldenItem(
                    id=f"{prefix}-mis-{index:03d}",
                    axis=EvaluationAxis.MIS_CITATION,
                    question=phrasing.missing_templates[
                        index % len(phrasing.missing_templates)
                    ].format(title=document, article=fake),
                    expected_outcome=ExpectedOutcome.NEEDS_VERIFICATION,
                    expected_document=document,
                    forbidden_clause_paths=(fake,),
                    expected_answer=phrasing.absent_answer,
                    notes=(
                        f"{document} ends at {highest_row.article} ({highest}); {fake} was never "
                        f"enacted. Answering confirms a premise that is false."
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
                    question=article.phrasing.deleted_template.format(
                        title=document, article=article.article
                    ),
                    expected_outcome=ExpectedOutcome.NEEDS_VERIFICATION,
                    expected_document=document,
                    forbidden_clause_paths=tuple(neighbours),
                    expected_answer=article.phrasing.vacant_answer,
                    notes=(
                        "Vacated provision. The failure mode is answering from the neighbouring "
                        "articles, whose citations resolve perfectly well and are still wrong."
                    ),
                )
            )
    return items


def generate_cross_domain(
    prefix: str,
    neighbours: Sequence[tuple[str, Sequence[Article]]],
    asking: Phrasing = phrasing_module.KOREAN,
    shared_documents: frozenset[str] = frozenset(),
) -> list[GoldenItem]:
    """Real obligations from the neighbouring cells, asked here with cross-cell off.

    The correct behaviour is to decline. Answering a cosmetic question out of device regulation is
    a *confident* wrong answer, which is the one failure mode worse than an empty one.

    **More than one neighbour is allowed and the budget is split evenly between them.** A
    cross-domain neighbour and a cross-authority one fail differently — the first tests that the
    cell scope holds between two corpora in the same language that already share Parts, the second
    that a question is not answered out of the wrong jurisdiction's law — and the axis measures
    whichever it is given. Which neighbours a cell has is configuration (``docs/eval/cells.json``),
    not a default reached for here.
    """
    usable = [
        (
            slug,
            [
                article
                for article in articles
                if article.usable and article.document not in shared_documents
            ],
        )
        for slug, articles in neighbours
    ]
    usable = [(slug, articles) for slug, articles in usable if articles]
    if not usable:
        return []

    total = TARGETS[EvaluationAxis.CROSS_DOMAIN]
    #: Split evenly, with the remainder going to the earliest neighbours so the count is exactly
    #: `total` however many neighbours there are — a short axis is a weaker denominator, and the
    #: whole reason the targets exist is that a per-axis score should not rest on a handful.
    share, extra = divmod(total, len(usable))
    items: list[GoldenItem] = []
    for position, (slug, articles) in enumerate(usable):
        for article in _spread(articles, share + (1 if position < extra else 0)):
            items.append(
                GoldenItem(
                    id=f"{prefix}-cross-{len(items) + 1:03d}",
                    axis=EvaluationAxis.CROSS_DOMAIN,
                    question=article.phrasing.cross_template.format(
                        title=article.document,
                        article=article.article,
                        heading=article.phrasing.display_heading(article.heading),
                    ),
                    expected_outcome=ExpectedOutcome.NEEDS_VERIFICATION,
                    expected_document=None,
                    cross_cell=False,
                    expected_answer=asking.wrong_cell_answer,
                    notes=f"Belongs to {slug}. Declining is correct (ADR-0006 decision 9).",
                )
            )
    return items


def build(
    session: Session,
    *,
    cell: str,
    neighbour_cells: Sequence[str],
    curated_path: Path,
    set_version: str,
) -> GoldenSet:
    """Generated axes plus the curated file, in one set.

    The curated file is the source of truth for the axes it covers: a re-seed regenerates the
    templated items and leaves hand-authored ones exactly as written.
    """
    registry = corpus.cells(session)
    unknown = [slug for slug in (cell, *neighbour_cells) if slug not in registry]
    if unknown:
        raise SystemExit(f"unknown cell: {', '.join(unknown)}")

    prefix = "samd" if registry[cell].domain == Domain.SAMD.value else "cos"
    articles = read_articles(session, registry[cell].id)
    neighbours = [(slug, read_articles(session, registry[slug].id)) for slug in neighbour_cells]
    #: The asking cell's own phrasing, taken from what it actually holds rather than from its slug —
    #: a cell is not annotated with a language and the versions under it are.
    asking = articles[0].phrasing if articles else phrasing_module.KOREAN
    #: Titles this cell claims itself. A neighbour's copy of one of these is not a wrong-cell
    #: question — it is this cell's own governing text seen from the other side of an M:N row.
    shared = frozenset(article.document for article in articles)

    items = [
        *generate_identifier(prefix, articles),
        *generate_mis_citation(prefix, articles),
        *generate_cross_domain(prefix, neighbours, asking, shared),
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
