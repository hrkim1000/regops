"""Reading the clause store — what phase 1.1's parse stage produced from an archived version.

Read-only, like the rest of this router set: everything that *writes* clauses is the pipeline
(CLAUDE.md § The seam). Three shapes decide the response:

- **Document order is `ordinal`, never `clause_path`.** The path is the address; the ordinal is the
  reading sequence. Sorting by path would file 제10조 between 제1조 and 제2조.
- **An annex table row is a `Clause`** (ADR-0014), so rows arrive in the same list as prose and
  carry their cells in ``row_columns``. The *ordered* header lives on the parent ``table`` clause
  and only there — ``jsonb`` does not preserve key order, so a row's object alone cannot say which
  column comes first.
- **A version with zero clauses is not always a defect.** An RSS board yields none by design
  ([phase1.1](../../../../../docs/plan/phase1.1_normalization.md) deviation 11), so the response
  states whether this document type is parseable at all rather than leaving the reader to guess
  between "not parsed yet" and "nothing to parse".
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from regops_shared.api import Meta, ok
from regops_shared.auth import Principal, get_current_principal
from regops_shared.db import AsyncSession, get_db

from ...models import Clause, Document, DocumentVersion
from ...parsing import is_parseable

router = APIRouter(prefix="/api/v1", tags=["regulation"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[Principal, Depends(get_current_principal)]

#: A page has to hold enough of a document for the tree to read as a tree — the 95th percentile
#: version has 309 clauses and the largest has 2,212, so this covers most instruments whole while
#: still bounding the response.
CLAUSE_PAGE_SIZE = 500
CLAUSE_PAGE_SIZE_MAX = 1000


@router.get("/document-versions/{version_id}/clauses")
async def list_clauses(
    version_id: uuid.UUID,
    db: DbSession,
    _: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(CLAUSE_PAGE_SIZE, ge=1, le=CLAUSE_PAGE_SIZE_MAX),
    clause_path: str | None = Query(
        None,
        description="Jump to the page holding this clause. What makes a citation a deep link.",
    ),
) -> dict[str, Any]:
    """The clauses of one version, in document order.

    404s on an unknown version rather than returning an empty list: "this version does not exist"
    and "this version has no clauses" are different answers, and only one of them is a bug.

    ``clause_path`` overrides ``page``. A citation names a clause, not a page number, and the
    largest version in the corpus holds 2,212 clauses — a "deep link" that lands the reader on page
    one of five is a link to the document, not to the evidence.
    """
    version = await db.get(DocumentVersion, version_id)
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Version not found")
    document = await db.get(Document, version.document_id)

    total = (
        await db.scalar(
            select(func.count()).select_from(Clause).where(Clause.document_version_id == version_id)
        )
        or 0
    )

    focus = await _page_of(db, version_id=version_id, clause_path=clause_path, page_size=page_size)
    if focus is not None:
        page = focus
    rows = list(
        await db.scalars(
            select(Clause)
            .where(Clause.document_version_id == version_id)
            .order_by(Clause.ordinal)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )

    return ok(
        {
            "version": {
                "id": str(version.id),
                "version_label": version.version_label,
                "language": version.language,
                "effective_date": (
                    version.effective_date.isoformat() if version.effective_date else None
                ),
                "effective_date_phrase": version.effective_date_phrase,
                "parser_version": version.parser_version,
            },
            "document": (
                {
                    "id": str(document.id),
                    "title": document.title,
                    "canonical_key": document.canonical_key,
                    "doc_type": document.doc_type.value,
                }
                if document
                else None
            ),
            #: Whether *this document type* yields clauses at all. False for a feed, where an empty
            #: list is the correct outcome and not an ingestion gap.
            "parseable": is_parseable(document.doc_type) if document else False,
            #: Echoed back only when it resolved. A caller that asked for a clause this version does
            #: not have gets page 1 and a null here, rather than a silent scroll to nowhere.
            "focus_clause_path": clause_path if focus is not None else None,
            "clauses": [_clause_out(clause) for clause in rows],
        },
        meta=Meta(page=page, page_size=page_size, total=total),
    )


async def _page_of(
    db: AsyncSession, *, version_id: uuid.UUID, clause_path: str | None, page_size: int
) -> int | None:
    """Which page holds ``clause_path``, or ``None`` if it does not resolve.

    Rank is counted by ``ordinal``, which is the reading order the listing sorts by — not by
    ``clause_path``, which would file 제10조 between 제1조 and 제2조 and send the reader to the
    wrong page with complete confidence.
    """
    if not clause_path:
        return None
    ordinal = await db.scalar(
        select(Clause.ordinal).where(
            Clause.document_version_id == version_id, Clause.clause_path == clause_path
        )
    )
    if ordinal is None:
        return None
    rank = (
        await db.scalar(
            select(func.count())
            .select_from(Clause)
            .where(Clause.document_version_id == version_id, Clause.ordinal < ordinal)
        )
        or 0
    )
    return rank // page_size + 1


def _clause_out(clause: Clause) -> dict[str, Any]:
    """One addressable unit.

    ``clause_path`` leads because it is what a Citation pins — the reader has to be able to see the
    address they would cite, not just the text. ``effective_date`` travels with its raw phrase for
    the same reason it does on a version (ADR-0013): a clause that states its own application date
    overrides its version's, and an unresolvable one must stay visibly unresolved.
    """
    return {
        "id": str(clause.id),
        "clause_path": clause.clause_path,
        "path_segments": clause.path_segments,
        "level": clause.level,
        "ordinal": clause.ordinal,
        "kind": clause.kind.value,
        "heading": clause.heading,
        "text": clause.text,
        #: On a ``table``: the ordered header labels. On a ``table_row``: ``{label: cell}``.
        #: The order lives on the table alone — ``jsonb`` sorts an object's keys.
        "row_columns": clause.row_columns,
        "effective_date": clause.effective_date.isoformat() if clause.effective_date else None,
        "effective_date_phrase": clause.effective_date_phrase,
        "parent_clause_id": str(clause.parent_clause_id) if clause.parent_clause_id else None,
        "source_ref": clause.source_ref,
        #: 조문변경여부 — the authority's own "this article changed" flag, stored for the 1.6
        #: reconciliation and shown here because it is the source's claim, not ours.
        "authority_changed": clause.authority_changed,
    }


__all__ = ["router"]
