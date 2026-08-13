"""Reading what changed between two versions — the clause diff, with both sides of the text.

The diff stage already resolves renumbering explicitly rather than reporting delete + add
(ADR-0002 decision 7); this router is what lets a reader *see* that. Three shapes decide the
response:

- **Both sides travel with the diff.** A `modified` row whose old text is a click away is a diff
  nobody reads, and "what actually changed" is the entire question an alert sends someone here to
  answer. The two clause rows are fetched by id from the pairing the diff stage established, so a
  renumber shows 제7조 → 제9조 with its text on both sides rather than as a removal beside an
  unrelated addition.
- **`match_basis` and `similarity` are exposed, not hidden.** A pairing the authority stated
  (조문이동이전/조문이동이후) and one we inferred from text similarity carry very different
  confidence, and `needs_review` marks the ones nobody has checked. A UI that rendered all three
  identically would present a guess as a fact.
- **Reading order is the new version's `ordinal`, falling back to the old one for a removal.**
  Sorting by `clause_path` files 제10조 between 제1조 and 제2조, which is the same mistake the
  clause listing avoids for the same reason.

Read-only, like the rest of this router set. `monitoring` composes alerts from `change_events` on
its own side of the seam and never reads through here — this endpoint serves the *reader*.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from regops_shared.api import Meta, ok
from regops_shared.auth import Principal, get_current_principal
from regops_shared.constants import ChangeKind
from regops_shared.db import AsyncSession, get_db

from ...models import Clause, ClauseDiff, Document, DocumentVersion

router = APIRouter(prefix="/api/v1", tags=["regulation"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[Principal, Depends(get_current_principal)]

DIFF_PAGE_SIZE = 100
DIFF_PAGE_SIZE_MAX = 500

#: Characters of clause text returned per side. A single 별표 clause in the gated corpus runs to
#: 340 KB, and a diff list that returned it whole would ship megabytes to render a change summary.
#: Truncation is **flagged on the row** so a reader is never shown a shortened clause believing it
#: is the whole one — the clause view has the full text, and the response says so.
DIFF_TEXT_MAX_CHARS = 4_000


@router.get("/document-versions/{version_id}/diffs")
async def list_diffs(
    version_id: uuid.UUID,
    db: DbSession,
    _: CurrentUser,
    change_kind: Annotated[
        list[ChangeKind] | None, Query(description="Filter by kind; default is every kind")
    ] = None,
    clause_path: Annotated[
        list[str] | None,
        Query(description="Only these paths — what an alert's clause list asks for"),
    ] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(DIFF_PAGE_SIZE, ge=1, le=DIFF_PAGE_SIZE_MAX),
) -> dict[str, Any]:
    """Every clause this version changed, with the old and new text side by side.

    404s on an unknown version rather than returning an empty list: "this version does not exist"
    and "this version changed nothing" are different answers, and a baseline ingestion legitimately
    produces the second one — the first version of a document is not an amendment, so it has no
    diffs at all and that is correct rather than missing.
    """
    version = await db.get(DocumentVersion, version_id)
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Version not found")
    document = await db.get(Document, version.document_id)

    predicates = [ClauseDiff.to_version_id == version_id]
    if change_kind:
        predicates.append(ClauseDiff.change_kind.in_(tuple(change_kind)))
    if clause_path:
        # Either side matches: an alert's clause list names the path in the *new* version, but a
        # removal only exists in the old one and would otherwise be unfindable from the alert.
        predicates.append(
            ClauseDiff.clause_path.in_(clause_path) | ClauseDiff.from_clause_path.in_(clause_path)
        )

    total = await db.scalar(select(func.count()).select_from(ClauseDiff).where(*predicates)) or 0
    rows = list(
        await db.scalars(
            select(ClauseDiff)
            .where(*predicates)
            .order_by(ClauseDiff.clause_path)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )

    clauses = await _clauses_by_id(
        db,
        [row.from_clause_id for row in rows] + [row.to_clause_id for row in rows],
    )
    ordinals = {clause_id: clause.ordinal for clause_id, clause in clauses.items()}
    # Reading order, not path order — 제10조 sorts before 제2조 as a string. A removal has no new
    # ordinal, so it falls back to where it sat in the old version, which keeps it beside its
    # neighbours instead of collapsing every removal to the top.
    rows.sort(
        key=lambda row: (
            ordinals.get(row.to_clause_id)
            if row.to_clause_id is not None
            else ordinals.get(row.from_clause_id, 0)
        )
        or 0
    )

    previous_id = next((row.from_version_id for row in rows if row.from_version_id), None)
    previous = await db.get(DocumentVersion, previous_id) if previous_id else None

    return ok(
        {
            "version": _version_out(version),
            "from_version": _version_out(previous) if previous else None,
            "document": (
                {
                    "id": str(document.id),
                    "title": document.title,
                    "doc_type": document.doc_type.value,
                }
                if document
                else None
            ),
            #: The first version of a document has no predecessor and therefore no diffs. Stated so
            #: an empty list reads as "nothing to compare against" rather than as a parse gap.
            "baseline": total == 0 and previous is None,
            "diffs": [_diff_out(row, clauses) for row in rows],
        },
        meta=Meta(page=page, page_size=page_size, total=total),
    )


# --- shaping ---------------------------------------------------------------------------------


async def _clauses_by_id(
    db: AsyncSession, clause_ids: list[uuid.UUID | None]
) -> dict[uuid.UUID, Clause]:
    """Both sides of a whole page in one query rather than two per row."""
    wanted = {value for value in clause_ids if value is not None}
    if not wanted:
        return {}
    rows = await db.scalars(select(Clause).where(Clause.id.in_(wanted)))
    return {clause.id: clause for clause in rows}


def _version_out(version: DocumentVersion) -> dict[str, Any]:
    return {
        "id": str(version.id),
        "version_label": version.version_label,
        "language": version.language,
        "effective_date": version.effective_date.isoformat() if version.effective_date else None,
        "published_at": version.published_at.isoformat() if version.published_at else None,
        "retrieved_at": version.retrieved_at.isoformat(),
    }


def _side(clause: Clause | None) -> dict[str, Any] | None:
    """One side of the comparison. ``None`` where the clause did not exist on that side."""
    if clause is None:
        return None
    text = clause.text or ""
    return {
        "clause_id": str(clause.id),
        "clause_path": clause.clause_path,
        "heading": clause.heading,
        "text": text[:DIFF_TEXT_MAX_CHARS],
        #: Never let a reader take a shortened clause for the whole one. The clause view has it in
        #: full, and this flag is what tells the UI to say so.
        "truncated": len(text) > DIFF_TEXT_MAX_CHARS,
        "kind": clause.kind.value,
    }


def _diff_out(diff: ClauseDiff, clauses: dict[uuid.UUID, Clause]) -> dict[str, Any]:
    """One changed clause.

    ``from_clause_path`` is the other side of a renumber and is null for everything else — which is
    exactly what lets a UI render 제7조 → 제9조 as a move rather than as two unrelated events.
    """
    return {
        "id": str(diff.id),
        "clause_path": diff.clause_path,
        "from_clause_path": diff.from_clause_path,
        "change_kind": diff.change_kind.value,
        #: How the pairing was established — ``authority`` (stated in 조문이동), ``path``,
        #: ``content_hash`` or ``similarity`` (inferred). Different confidence, shown as different.
        "match_basis": diff.match_basis,
        "similarity": diff.similarity,
        #: A low-confidence renumber match was written *and* queued: dropping it loses the change,
        #: accepting it silently asserts an identity nobody checked.
        "needs_review": diff.needs_review,
        "from": _side(clauses.get(diff.from_clause_id) if diff.from_clause_id else None),
        "to": _side(clauses.get(diff.to_clause_id) if diff.to_clause_id else None),
    }


__all__ = ["router"]
