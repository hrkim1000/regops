"""Everything the harness reads out of the database, in one place and read-only.

Raw SQL throughout, and not for performance. The harness reads tables owned by all four services —
``clauses`` and ``irs`` from `regulation`, ``answers`` from `assistant`, ``alerts`` from
`monitoring`, ``users`` from `platform-core` — so importing any one service's ORM models would make
an evaluation tool a dependent of that service's internals, which is the coupling CLAUDE.md § Table
ownership exists to prevent. It writes nothing.

Everything here is executed with :func:`~regops_shared.db.sync_session`: the harness is a script,
not a request handler, and a sync session is the shape that survives being called from a plain
``main()``.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from .goldenset import article_of


@dataclass(frozen=True, slots=True)
class CellRow:
    id: uuid.UUID
    slug: str
    authority: str
    domain: str


@dataclass(frozen=True, slots=True)
class VersionRow:
    id: uuid.UUID
    document_id: uuid.UUID
    title: str
    doc_type: str
    effective_date: str | None
    clause_count: int


def cells(session: Session) -> dict[str, CellRow]:
    rows = session.execute(
        text("SELECT id, slug, authority::text, domain::text FROM cells ORDER BY slug")
    )
    return {row[1]: CellRow(row[0], row[1], row[2], row[3]) for row in rows}


def cell_versions(session: Session, cell_id: uuid.UUID) -> list[VersionRow]:
    """Every version of every parent document claimed by a cell, newest effective date first.

    Parent documents only: an annex is a child ``Document`` (ADR-0014), and a golden item names the
    instrument a reader would name.
    """
    rows = session.execute(
        text(
            """
            SELECT dv.id, d.id, d.title, d.doc_type::text, dv.effective_date::text,
                   (SELECT count(*) FROM clauses c WHERE c.document_version_id = dv.id)
            FROM document_versions dv
            JOIN documents d ON d.id = dv.document_id
            JOIN document_cells dc ON dc.document_id = d.id
            WHERE dc.cell_id = :cell_id AND d.parent_document_id IS NULL
            ORDER BY d.title, dv.effective_date DESC NULLS LAST
            """
        ),
        {"cell_id": cell_id},
    )
    return [VersionRow(*row) for row in rows]


def in_force_versions(session: Session, cell_id: uuid.UUID) -> dict[str, VersionRow]:
    """One version per document title: the latest whose effective date has arrived.

    Derived, never stored (ADR-0016 decision 6), and computed over the whole version set because
    "which one is in force" is a property of the set rather than of a row.
    """
    latest: dict[str, VersionRow] = {}
    today = datetime.now(UTC).date().isoformat()
    for row in cell_versions(session, cell_id):
        if row.effective_date is None or row.effective_date > today:
            continue
        held = latest.get(row.title)
        if held is None or (row.effective_date or "") > (held.effective_date or ""):
            latest[row.title] = row
    return latest


def articles(session: Session, version_id: uuid.UUID) -> list[tuple[str, str | None]]:
    """``(clause_path, heading)`` for every 조 in a version, in document order.

    Matched on the path rather than on ``level``: the corpus nests some 조 under 절 and some
    directly under 장, so a level filter drops a whole chapter — 화장품법 제3장 among them.
    """
    rows = session.execute(
        text(
            """
            SELECT clause_path, heading FROM clauses
            WHERE document_version_id = :version_id
              AND kind = 'prose'
              AND clause_path ~ '(^|/)제[0-9]+조(의[0-9]+)?$'
            ORDER BY ordinal
            """
        ),
        {"version_id": version_id},
    )
    return [(row[0], row[1]) for row in rows]


def article_index(session: Session, cell_id: uuid.UUID) -> dict[str, set[str]]:
    """``{document title: {제5조, 제5조의2, …}}`` across every version the cell claims.

    Across versions on purpose: a golden item may pin an expectation to a clause that only exists
    in a not-yet-in-force version, which is exactly what the effective-date axis is for.
    """
    rows = session.execute(
        text(
            """
            SELECT DISTINCT d.title, c.clause_path
            FROM clauses c
            JOIN document_versions dv ON dv.id = c.document_version_id
            JOIN documents d ON d.id = dv.document_id
            JOIN document_cells dc ON dc.document_id = d.id
            WHERE dc.cell_id = :cell_id
              AND c.clause_path ~ '(^|/)제[0-9]+조(의[0-9]+)?$'
            """
        ),
        {"cell_id": cell_id},
    )
    index: dict[str, set[str]] = {}
    for title, path in rows:
        index.setdefault(title, set()).add(article_of(path))
    return index


def citations_resolve(
    session: Session, pairs: Sequence[tuple[uuid.UUID, str]]
) -> dict[tuple[uuid.UUID, str], bool]:
    """Does a clause exist at each ``(version, path)``?

    Suffix-tolerant, because the stored citation path is not normalised: the corpus holds
    ``제2장/제8조`` and answers carry ``제8조``, ``제2장/제8조`` and ``제8조/제1호`` for the same
    provision. Requiring exact equality would report a correct citation as a fabrication — the one
    direction that would make the hallucination gate look worse than the system is, and equally
    the one that would make a real fabrication indistinguishable from a formatting difference.
    """
    resolved: dict[tuple[uuid.UUID, str], bool] = {}
    for version_id, path in dict.fromkeys(pairs):
        hit = session.execute(
            text(
                """
                SELECT 1 FROM clauses
                WHERE document_version_id = :version_id
                  AND (clause_path = :path OR clause_path LIKE :suffix)
                LIMIT 1
                """
            ),
            {"version_id": version_id, "path": path, "suffix": f"%/{path}"},
        ).first()
        resolved[(version_id, path)] = hit is not None
    return resolved


def ir_counts(session: Session, version_id: uuid.UUID, domain: str) -> dict[str, int]:
    """IRs per source clause path, for one version under one domain profile.

    Keyed by the 조-level path the RA marks at, because that is the unit the atomicity rule is
    stated in and the unit ground-truth markup records.
    """
    rows = session.execute(
        text(
            """
            SELECT c.clause_path, count(DISTINCT i.id)
            FROM irs i
            JOIN ir_citations ic ON ic.ir_id = i.id
            JOIN clauses c ON c.id = ic.clause_id
            WHERE ic.document_version_id = :version_id AND i.domain_profile = :domain
            GROUP BY 1
            """
        ),
        {"version_id": version_id, "domain": domain},
    )
    return {row[0]: row[1] for row in rows}


def ir_counts_for_run(session: Session, run_id: uuid.UUID) -> dict[str, int]:
    """IRs per clause path attributed to one extraction run — the determinism comparison.

    Per run rather than per version: re-extracting leaves both runs' rows in the store, so a
    version-level count would sum two passes and report perfect stability by addition.
    """
    rows = session.execute(
        text(
            """
            SELECT c.clause_path, count(DISTINCT i.id)
            FROM irs i
            JOIN ir_citations ic ON ic.ir_id = i.id
            JOIN clauses c ON c.id = ic.clause_id
            WHERE i.extraction_run_id = :run_id
            GROUP BY 1
            """
        ),
        {"run_id": run_id},
    )
    return {row[0]: row[1] for row in rows}


def extraction_runs(
    session: Session, version_id: uuid.UUID, domain: str, *, limit: int = 2
) -> list[tuple[uuid.UUID, str]]:
    """The most recent runs for a ``(version, domain)`` with their regime, newest first."""
    rows = session.execute(
        text(
            """
            SELECT id, rule_version || '/' || prompt_version || '/' || llm_model
                   || '@' || coalesce(temperature::text, 'null')
            FROM extraction_runs
            WHERE document_version_id = :version_id AND domain_profile = :domain
              AND status = 'completed'
            ORDER BY started_at DESC LIMIT :limit
            """
        ),
        {"version_id": version_id, "domain": domain, "limit": limit},
    )
    return [(row[0], row[1]) for row in rows]


def ir_citation_resolution(session: Session, version_id: uuid.UUID) -> tuple[int, int]:
    """``(citations, resolving)`` for one version's IRs.

    ``ir_citations.clause_id`` is a foreign key, so a dangling citation cannot exist — the check
    that matters is whether the cited clause belongs to the version the citation names, which a
    foreign key does not constrain.
    """
    row = session.execute(
        text(
            """
            SELECT count(*),
                   count(*) FILTER (WHERE c.document_version_id = ic.document_version_id)
            FROM ir_citations ic
            JOIN clauses c ON c.id = ic.clause_id
            WHERE ic.document_version_id = :version_id
            """
        ),
        {"version_id": version_id},
    ).one()
    return int(row[0]), int(row[1])


def latest_extraction_run(session: Session, version_id: uuid.UUID, domain: str) -> str | None:
    """The regime the newest run for this ``(version, domain)`` ran at, rendered for a report.

    ``temperature`` comes off the row rather than out of the constant: ADR-0017 pins it to 0 and
    treats drift as a regression, which is only checkable if the value actually used is stored
    rather than read back from a constant that has since been edited.
    """
    row = session.execute(
        text(
            """
            SELECT rule_version, prompt_version, llm_model, temperature
            FROM extraction_runs
            WHERE document_version_id = :version_id AND domain_profile = :domain
            ORDER BY started_at DESC LIMIT 1
            """
        ),
        {"version_id": version_id, "domain": domain},
    ).first()
    if row is None:
        return None
    return f"rule={row[0]} prompt={row[1]} model={row[2]} temperature={row[3]}"


@dataclass(frozen=True, slots=True)
class ScheduleRow:
    source_id: uuid.UUID
    label: str
    interval_seconds: int
    enabled: bool
    created_at: datetime
    observations: int


def schedules_with_observations(session: Session, *, days: int) -> list[ScheduleRow]:
    """Every scheduled source with the observations it actually produced in the window.

    The join is a LEFT JOIN and the count is filtered rather than the rows: a source that produced
    no observation at all must appear with zero, because it is the entire failure this measurement
    exists to expose. An inner join would drop exactly the sources that were never polled.
    """
    since = datetime.now(UTC) - timedelta(days=days)
    rows = session.execute(
        text(
            """
            SELECT ss.source_id,
                   s.title,
                   ss.interval_seconds,
                   ss.enabled,
                   ss.created_at,
                   (SELECT count(*) FROM fetch_observations fo
                     WHERE fo.source_id = ss.source_id AND fo.fetched_at >= :since)
            FROM source_schedules ss
            JOIN sources s ON s.id = ss.source_id
            ORDER BY s.title
            """
        ),
        {"since": since},
    )
    return [ScheduleRow(*row) for row in rows]


def change_events_by_cell(session: Session, *, days: int) -> dict[str, int]:
    since = datetime.now(UTC) - timedelta(days=days)
    rows = session.execute(
        text(
            """
            SELECT c.slug, count(*) FROM change_events ce
            JOIN cells c ON c.id = ce.cell_id
            WHERE ce.created_at >= :since
            GROUP BY 1
            """
        ),
        {"since": since},
    )
    return {row[0]: row[1] for row in rows}


def amendment_versions(session: Session, cell_slug: str, *, days: int) -> set[str]:
    """Document versions in a cell that produced at least one clause diff in the window.

    This is the system's own account of what it saw. It is **not** the detection-coverage
    denominator: that is the authority's list of what it actually published, which only a person
    comparing against the source can supply.
    """
    since = datetime.now(UTC) - timedelta(days=days)
    rows = session.execute(
        text(
            """
            SELECT DISTINCT d.title || ' @ ' || coalesce(dv.effective_date::text, '미해석')
            FROM clause_diffs cd
            JOIN document_versions dv ON dv.id = cd.to_version_id
            JOIN documents d ON d.id = dv.document_id
            JOIN document_cells dc ON dc.document_id = d.id
            JOIN cells c ON c.id = dc.cell_id
            WHERE c.slug = :slug AND cd.created_at >= :since
            """
        ),
        {"slug": cell_slug, "since": since},
    )
    return {row[0] for row in rows}


def weekly_query_users(session: Session, *, weeks: int) -> list[set[str]]:
    """Distinct askers per ISO week, oldest first, over the last ``weeks`` complete weeks.

    Read from ``queries`` rather than from a login event: the retention gate is *voluntary use*,
    and a session opened without a question asked is not use.
    """
    since = datetime.now(UTC) - timedelta(weeks=weeks)
    rows = session.execute(
        text(
            """
            SELECT date_trunc('week', asked_at) AS week, asked_by::text
            FROM queries
            WHERE asked_at >= :since AND asked_by IS NOT NULL
            GROUP BY 1, 2
            ORDER BY 1
            """
        ),
        {"since": since},
    )
    buckets: dict[datetime, set[str]] = {}
    for week, user in rows:
        buckets.setdefault(week, set()).add(user)
    # A week nobody used the system produces no row at all, and the retention scorer needs
    # *consecutive* weeks — so a silent gap would read as continuity. Materialise every week in
    # the window, empty ones included.
    first = min(buckets) if buckets else datetime.now(UTC)
    span = [first + timedelta(weeks=index) for index in range(weeks)]
    return [buckets.get(week, set()) for week in span]


def user_id_for(session: Session, email: str) -> tuple[uuid.UUID, str] | None:
    row = session.execute(
        text("SELECT id, role::text FROM users WHERE email = :email"), {"email": email}
    ).first()
    return (row[0], row[1]) if row else None


def clause_texts(
    session: Session, version_id: uuid.UUID, paths: Iterable[str], *, limit_chars: int = 1200
) -> dict[str, str]:
    """Clause text for the blind worksheet, bounded and marked when it was cut.

    A shortened clause shown as if whole is worse than no clause: an assessor judges "does this
    support the claim" from text that was cut away, and answers confidently.
    """
    out: dict[str, str] = {}
    for path in dict.fromkeys(paths):
        row = session.execute(
            text(
                """
                SELECT text FROM clauses
                WHERE document_version_id = :version_id
                  AND (clause_path = :path OR clause_path LIKE :suffix)
                ORDER BY length(clause_path)
                LIMIT 1
                """
            ),
            {"version_id": version_id, "path": path, "suffix": f"%/{path}"},
        ).first()
        if row is None:
            continue
        body = str(row[0])
        out[path] = (
            body if len(body) <= limit_chars else body[:limit_chars] + "\n…[본문 일부 생략됨]"
        )
    return out


__all__ = [
    "CellRow",
    "ScheduleRow",
    "VersionRow",
    "amendment_versions",
    "article_index",
    "articles",
    "cell_versions",
    "cells",
    "change_events_by_cell",
    "citations_resolve",
    "clause_texts",
    "extraction_runs",
    "in_force_versions",
    "ir_citation_resolution",
    "ir_counts",
    "ir_counts_for_run",
    "latest_extraction_run",
    "schedules_with_observations",
    "user_id_for",
    "weekly_query_users",
]
