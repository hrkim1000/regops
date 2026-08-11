"""Every read `assistant` makes across the service boundary, in one place.

`regulation` owns the clause store; `assistant` answers from it. CLAUDE.md § Table ownership makes
the rule explicit — *reads across a boundary are raw SQL; never import another service's model* —
and keeping all of them here means the seam is one file a reviewer can check rather than a habit
scattered through six.

Nothing in this module writes. The only tables `assistant` writes are its own, through the ORM.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from regops_shared.constants import FTS_CONFIG

from .passages import ClauseRow

#: Korean is agglutinative and PostgreSQL ships no Korean stemmer, so the ``simple`` configuration
#: indexes 화장품의 and 화장품 as different tokens. Both directions are covered with prefix queries:
#: the user's token as a prefix (catches 화장품 → 화장품의) and the token minus a trailing particle
#: (catches 화장품의 → 화장품). A heuristic, and labelled as one — ADR-0006 open question 2 leaves
#: lexical/vector weighting to be tuned against the golden set, and this is part of what gets tuned.
_PARTICLE_STRIP_MIN_LEN = 3

#: Shortest column value that may be matched as a *prefix of the query*. A 등급 cell holds ``2`` and
#: a 연번 cell holds ``59``; letting those match by prefix would return a large slice of 별표 1 for
#: any question containing a number.
ANNEX_MIN_VALUE_LEN = 4

#: Characters tsquery treats as operators. Stripped rather than escaped: a query is user text, and
#: letting `&`/`|`/`!` through would let a question silently become a boolean expression.
_TSQUERY_UNSAFE = re.compile(r"[^\w가-힣ㄱ-ㆎ.\-/§]+", re.UNICODE)


@dataclass(frozen=True, slots=True)
class VersionRef:
    """One pinned version. Retrieval never says "latest" — it says which one, and records it."""

    version_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    effective_date: date | None
    language: str


@dataclass(frozen=True, slots=True)
class Hit:
    """One retrieved clause, with the arm that found it and what it scored there."""

    clause_id: uuid.UUID
    clause_path: str
    document_version_id: uuid.UUID
    heading: str | None
    text: str
    kind: str
    effective_date: date | None
    score: float
    #: Every clause path the retrieved passage covers. Generation may cite any of them; that is how
    #: retrieval stays coarse while citation stays fine (ADR-0006 decision 1).
    child_clause_paths: tuple[str, ...] = ()
    #: The assembled 조-level passage the vector actually matched, where that arm supplied one.
    #: Preferred over ``text`` when building the prompt: it is bounded, and it is the unit retrieval
    #: scored — showing the model something else invites it to cite what it was not matched on.
    passage: str | None = None


# --- version scoping -------------------------------------------------------------------------


def versions_in_scope(
    session: Session,
    *,
    cell_ids: list[uuid.UUID],
    today: date,
    version_ids: list[uuid.UUID] | None = None,
) -> list[VersionRef]:
    """The version of each in-scope document that retrieval will target.

    One version per document, chosen explicitly: the latest whose effective date has arrived, else
    the nearest pending one, else the most recently retrieved. "Latest" is never implicit — the
    chosen ids are recorded on the answer, so a stored answer can be re-checked against exactly the
    text it was written from.

    ``version_ids`` pins the scope outright, which is what a golden-set run and a re-verification
    both need: the same question against the same versions has to be reproducible after an
    amendment lands.
    """
    if version_ids:
        rows = session.execute(
            text(
                """
                SELECT dv.id, dv.document_id, d.title, dv.effective_date, dv.language
                FROM document_versions dv
                JOIN documents d ON d.id = dv.document_id
                WHERE dv.id = ANY(:version_ids)
                """
            ),
            {"version_ids": version_ids},
        ).all()
    elif cell_ids:
        rows = session.execute(
            text(
                """
                SELECT DISTINCT ON (dv.document_id)
                       dv.id, dv.document_id, d.title, dv.effective_date, dv.language
                FROM document_versions dv
                JOIN documents d ON d.id = dv.document_id
                JOIN document_cells dc ON dc.document_id = dv.document_id
                WHERE dc.cell_id = ANY(:cell_ids)
                  AND dv.parser_version IS NOT NULL
                  AND d.doc_type <> 'feed'
                ORDER BY dv.document_id,
                         (dv.effective_date IS NOT NULL AND dv.effective_date <= :today) DESC,
                         CASE WHEN dv.effective_date <= :today THEN dv.effective_date END
                             DESC NULLS LAST,
                         dv.effective_date ASC NULLS LAST,
                         dv.retrieved_at DESC
                """
            ),
            {"cell_ids": cell_ids, "today": today},
        ).all()
    else:
        return []

    return [
        VersionRef(
            version_id=row[0],
            document_id=row[1],
            document_title=row[2],
            effective_date=row[3],
            language=row[4],
        )
        for row in rows
    ]


def cell_ids_for(session: Session, *, cell_id: uuid.UUID, cross_cell: bool) -> list[uuid.UUID]:
    """The cells retrieval may draw from.

    Cross-cell is an explicit mode, never the default (ADR-0006 decision 9): a cosmetic question
    answered from device regulation is a confident wrong answer, and it is the worst failure this
    product can produce.
    """
    if not cross_cell:
        return [cell_id]
    return [row[0] for row in session.execute(text("SELECT id FROM cells")).all()]


def cell_domain(session: Session, cell_id: uuid.UUID) -> str | None:
    """The domain a cell belongs to. What the "needs verification" rate is grouped by."""
    row = session.execute(
        text("SELECT domain::text FROM cells WHERE id = :id"), {"id": cell_id}
    ).first()
    return row[0] if row else None


# --- clause reads ----------------------------------------------------------------------------


def load_clauses(session: Session, version_id: uuid.UUID) -> list[ClauseRow]:
    """Every clause of one version, in document order, for passage assembly."""
    rows = session.execute(
        text(
            """
            SELECT id, clause_path, kind::text, heading, text, ordinal, parent_clause_id,
                   row_columns
            FROM clauses
            WHERE document_version_id = :version_id
            ORDER BY ordinal
            """
        ),
        {"version_id": version_id},
    ).all()
    return [
        ClauseRow(
            id=row[0],
            clause_path=row[1],
            kind=row[2],
            heading=row[3],
            text=row[4],
            ordinal=row[5],
            parent_clause_id=row[6],
            row_columns=row[7],
        )
        for row in rows
    ]


def version_meta(session: Session, version_id: uuid.UUID) -> VersionRef | None:
    """One version and its document title, for passage headers. ``None`` if it does not exist."""
    row = session.execute(
        text(
            """
            SELECT dv.id, dv.document_id, d.title, dv.effective_date, dv.language
            FROM document_versions dv
            JOIN documents d ON d.id = dv.document_id
            WHERE dv.id = :version_id
            """
        ),
        {"version_id": version_id},
    ).first()
    if row is None:
        return None
    return VersionRef(
        version_id=row[0],
        document_id=row[1],
        document_title=row[2],
        effective_date=row[3],
        language=row[4],
    )


def clauses_by_path(
    session: Session, *, version_ids: list[uuid.UUID], clause_paths: list[str]
) -> dict[tuple[uuid.UUID, str], Hit]:
    """Resolve ``(version, path)`` pairs to their clause text.

    This is what turns a model's citation into evidence. A path that resolves to nothing here is a
    fabricated citation, and decision 4 rejects it mechanically before any model sees it again.
    """
    if not version_ids or not clause_paths:
        return {}
    rows = session.execute(
        text(
            """
            SELECT c.id, c.clause_path, c.document_version_id, c.heading, c.text, c.kind::text,
                   coalesce(c.effective_date, dv.effective_date)
            FROM clauses c
            JOIN document_versions dv ON dv.id = c.document_version_id
            WHERE c.document_version_id = ANY(:version_ids)
              AND c.clause_path = ANY(:clause_paths)
            """
        ),
        {"version_ids": version_ids, "clause_paths": clause_paths},
    ).all()
    return {(row[2], row[1]): _hit(row, score=0.0) for row in rows}


# --- retrieval arms --------------------------------------------------------------------------


def lexical_search(
    session: Session, *, query: str, version_ids: list[uuid.UUID], limit: int
) -> list[Hit]:
    """BM25-style ranking over clause text (ADR-0006 decision 3, lexical arm).

    Table rows are excluded: they are served by :func:`annex_row_lookup`, which matches the
    identifier column exactly instead of ranking thousands of near-identical lines against each
    other.
    """
    tsquery = build_tsquery(query)
    if not tsquery or not version_ids:
        return []
    rows = session.execute(
        text(
            f"""
            SELECT c.id, c.clause_path, c.document_version_id, c.heading, c.text, c.kind::text,
                   coalesce(c.effective_date, dv.effective_date),
                   ts_rank_cd(
                       to_tsvector('{FTS_CONFIG}',
                                   coalesce(c.heading, '') || ' ' || coalesce(c.text, '')),
                       to_tsquery('{FTS_CONFIG}', :tsquery)
                   ) AS rank
            FROM clauses c
            JOIN document_versions dv ON dv.id = c.document_version_id
            WHERE c.document_version_id = ANY(:version_ids)
              AND c.kind <> 'table_row'
              AND to_tsvector('{FTS_CONFIG}',
                              coalesce(c.heading, '') || ' ' || coalesce(c.text, ''))
                  @@ to_tsquery('{FTS_CONFIG}', :tsquery)
            ORDER BY rank DESC, c.ordinal
            LIMIT :limit
            """
        ),
        {"tsquery": tsquery, "version_ids": version_ids, "limit": limit},
    ).all()
    return [_hit(row, score=float(row[7])) for row in rows]


def vector_search(
    session: Session, *, embedding: list[float], version_ids: list[uuid.UUID], limit: int
) -> list[Hit]:
    """Cosine nearest neighbours over the passage index (vector arm).

    The join back to ``clauses`` is what keeps citation finer than retrieval: the vector matched a
    passage, and the hit carries every clause path that passage covers.
    """
    if not version_ids or not embedding:
        return []
    literal = "[" + ",".join(repr(float(value)) for value in embedding) + "]"
    rows = session.execute(
        text(
            """
            SELECT c.id, c.clause_path, e.document_version_id, c.heading, c.text, c.kind::text,
                   coalesce(c.effective_date, dv.effective_date),
                   1 - (e.embedding <=> CAST(:vec AS vector)) AS similarity,
                   e.child_clause_paths, e.passage
            FROM clause_embeddings e
            JOIN clauses c ON c.id = e.clause_id
            JOIN document_versions dv ON dv.id = e.document_version_id
            WHERE e.document_version_id = ANY(:version_ids)
            ORDER BY e.embedding <=> CAST(:vec AS vector)
            LIMIT :limit
            """
        ),
        {"vec": literal, "version_ids": version_ids, "limit": limit},
    ).all()
    return [
        _hit(row, score=float(row[7]), child_clause_paths=tuple(row[8] or ()), passage=row[9])
        for row in rows
    ]


def identifier_lookup(
    session: Session, *, identifiers: list[str], version_ids: list[uuid.UUID], limit: int
) -> list[Hit]:
    """Resolve clause identifiers the query named outright — exactly, not fuzzily.

    *"화장품법 제8조"* is a lookup, not a search. A clause number has no useful embedding, and
    a lexical rank over one competes with every other article that happens to mention it.
    """
    if not identifiers or not version_ids:
        return []
    rows = session.execute(
        text(
            """
            SELECT c.id, c.clause_path, c.document_version_id, c.heading, c.text, c.kind::text,
                   coalesce(c.effective_date, dv.effective_date)
            FROM clauses c
            JOIN document_versions dv ON dv.id = c.document_version_id
            WHERE c.document_version_id = ANY(:version_ids)
              AND (c.clause_path = ANY(:identifiers) OR c.path_segments && :identifiers)
            ORDER BY c.ordinal
            LIMIT :limit
            """
        ),
        {"identifiers": identifiers, "version_ids": version_ids, "limit": limit},
    ).all()
    return [_hit(row, score=1.0) for row in rows]


def annex_row_lookup(
    session: Session, *, terms: list[str], version_ids: list[uuid.UUID], limit: int
) -> list[Hit]:
    """Exact-then-prefix match against an annex table row's own columns (decision 2).

    The question a user actually asks is *"갈라민트리에치오다이드는 사용할 수 있나?"* or
    *"CAS 65-29-2 의 사용한도는?"*. Both name a value in a column, so this matches the column rather
    than ranking the row's prose against a query — which is why the rows never needed to be embedded
    in the first place. ADR-0014 put the row in ``clauses`` with its columns in ``row_columns``, so
    this is one predicate against one table.
    """
    if not terms or not version_ids:
        return []
    rows = session.execute(
        text(
            """
            SELECT c.id, c.clause_path, c.document_version_id, c.heading, c.text, c.kind::text,
                   coalesce(c.effective_date, dv.effective_date),
                   max(CASE WHEN kv.value = ANY(:terms) THEN 1.0 ELSE 0.6 END) AS score
            FROM clauses c
            JOIN document_versions dv ON dv.id = c.document_version_id
            CROSS JOIN LATERAL jsonb_each_text(c.row_columns) AS kv(key, value)
            WHERE c.document_version_id = ANY(:version_ids)
              AND c.kind = 'table_row'
              AND c.row_columns IS NOT NULL
              AND (
                    kv.value = ANY(:terms)
                 OR kv.value ILIKE ANY(:prefixes)
                 -- The other direction, for agglutinative languages: the user typed
                 -- 갈라민트리에치오다이드**는** and the column holds the bare name. Guarded by
                 -- length, because a two-character cell value is a 등급 or a 연번 and would
                 -- prefix-match a large fraction of the question.
                 OR (length(kv.value) >= :min_value_len
                     AND EXISTS (SELECT 1 FROM unnest(:terms) AS t(term)
                                 WHERE t.term ILIKE kv.value || '%'))
              )
            GROUP BY c.id, c.clause_path, c.document_version_id, c.heading, c.text, c.kind,
                     c.effective_date, dv.effective_date, c.ordinal
            ORDER BY score DESC, c.ordinal
            LIMIT :limit
            """
        ),
        {
            "terms": terms,
            "prefixes": [f"{term}%" for term in terms],
            "min_value_len": ANNEX_MIN_VALUE_LEN,
            "version_ids": version_ids,
            "limit": limit,
        },
    ).all()
    return [_hit(row, score=float(row[7])) for row in rows]


# --- helpers ---------------------------------------------------------------------------------


def build_tsquery(query: str) -> str:
    """An OR-of-prefixes tsquery, tolerant of Korean particles.

    ``plainto_tsquery`` ANDs its terms, which over a Korean corpus indexed with the ``simple``
    configuration returns nothing far too often: 화장품의 and 화장품 are different tokens, so an AND
    of the user's exact surface forms rarely matches. OR-of-prefixes trades some precision for
    recall and lets ``ts_rank_cd`` sort out how many terms actually hit — the right trade when the
    vector arm is there to catch the paraphrases.
    """
    terms: list[str] = []
    for raw in _TSQUERY_UNSAFE.split(query or ""):
        token = raw.strip().lower()
        if not token:
            continue
        terms.append(f"{token}:*")
        if len(token) > _PARTICLE_STRIP_MIN_LEN and _is_hangul(token[-1]):
            terms.append(f"{token[:-1]}:*")
    # Deduplicate while keeping order — a repeated term adds nothing to an OR and costs index work.
    return " | ".join(dict.fromkeys(terms))


def _is_hangul(char: str) -> bool:
    return "가" <= char <= "힣"


def _hit(
    row: Sequence[Any],
    *,
    score: float,
    child_clause_paths: tuple[str, ...] = (),
    passage: str | None = None,
) -> Hit:
    """Shape one result row. Every arm selects the same seven leading columns, in the same order —
    which is the only reason one constructor can serve four different queries."""
    columns = tuple(row)
    return Hit(
        clause_id=columns[0],
        clause_path=columns[1],
        document_version_id=columns[2],
        heading=columns[3],
        text=columns[4],
        kind=columns[5],
        effective_date=columns[6],
        score=score,
        child_clause_paths=child_clause_paths,
        passage=passage,
    )


__all__ = [
    "Hit",
    "VersionRef",
    "annex_row_lookup",
    "build_tsquery",
    "cell_domain",
    "cell_ids_for",
    "clauses_by_path",
    "identifier_lookup",
    "lexical_search",
    "load_clauses",
    "vector_search",
    "version_meta",
    "versions_in_scope",
]
