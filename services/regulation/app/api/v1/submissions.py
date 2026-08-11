"""Reading submission requirements — *what must be filed for this procedure*.

Read-only and derived on the fly (:mod:`app.submissions`); nothing here writes and nothing is
stored. Two shapes decide the response:

- **Every document item carries its own `clause_path`.** The item *is* a clause, so the answer is
  citation-native rather than citation-annotated — "no answer without evidence" is satisfied by the
  data's shape, not by a check bolted on afterwards.
- **`caveats` is a field, not a footnote.** 40% of these procedures are conditional. A client that
  renders a checkbox list must be able to *refuse* to, on a machine-readable signal — a caveat
  buried in prose is one the UI silently drops, and a conditional list shown as a definitive one is
  exactly the error the gap-analysis pillar exists to catch.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from regops_shared.api import Meta, ok
from regops_shared.auth import Principal, get_current_principal
from regops_shared.db import AsyncSession, get_db

from ...models import Document, DocumentVersion
from ...submissions import Caveat, RequiredDocument, SubmissionRequirement, derive

router = APIRouter(prefix="/api/v1", tags=["regulation"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[Principal, Depends(get_current_principal)]

#: What each caveat means, for a client that has no business re-deriving the reasoning. English
#: because it is a contract field; the UI supplies its own copy.
CAVEAT_MEANING: dict[str, str] = {
    Caveat.CONDITIONAL_PROCEDURE: "The procedure clause is itself qualified — it may not apply.",
    Caveat.CONDITIONAL_ITEMS: "Some items apply only in stated cases; read each condition.",
    Caveat.DELEGATED_ITEMS: "Some items defer to another instrument; the list is incomplete here.",
    Caveat.NESTED_ITEMS: "Some items expand into 목; their children hold the detail.",
    Caveat.CROSS_INSTRUMENT: (
        "The enabling clause is in another law; this version may not state all of it."
    ),
    Caveat.NO_ITEMS_PARSED: (
        "The clause enumerates, but its items are inline rather than child clauses."
    ),
}


@router.get("/document-versions/{version_id}/submission-requirements")
async def list_submission_requirements(
    version_id: uuid.UUID, db: DbSession, _: CurrentUser
) -> dict[str, Any]:
    """Every filing requirement this version states, in document order.

    404s on an unknown version rather than returning an empty list: "this version does not exist"
    and "this version states no filing requirement" are different answers, and the second is
    ordinary — most instruments state none.
    """
    version = await db.get(DocumentVersion, version_id)
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Version not found")
    document = await db.get(Document, version.document_id)

    requirements = await db.run_sync(lambda sync: derive(sync, version_id))

    return ok(
        {
            "version": {
                "id": str(version.id),
                "version_label": version.version_label,
                "effective_date": (
                    version.effective_date.isoformat() if version.effective_date else None
                ),
                "effective_date_phrase": version.effective_date_phrase,
            },
            "document": (
                {
                    "id": str(document.id),
                    "title": document.title,
                    "canonical_key": document.canonical_key,
                }
                if document
                else None
            ),
            "requirements": [_requirement_out(item) for item in requirements],
        },
        meta=Meta(total=len(requirements)),
    )


def _requirement_out(requirement: SubmissionRequirement) -> dict[str, Any]:
    return {
        "clause_id": str(requirement.clause_id),
        #: The citation for the *obligation*. Each document below carries its own.
        "clause_path": requirement.clause_path,
        "heading": requirement.heading,
        "text": requirement.text,
        #: Verbatim as the clause writes it. Not resolved to a Document — cross-reference
        #: resolution is a separate stage (phase 2.1), and a guessed link is unverified evidence.
        "form_reference": requirement.form_reference,
        "recipient": requirement.recipient,
        #: False for most of these. A client should treat true as the exception, not the default.
        "is_definitive": requirement.is_definitive,
        "caveats": [
            {"code": caveat.value, "meaning": CAVEAT_MEANING[caveat]}
            for caveat in requirement.caveats
        ],
        "documents": [_document_out(document) for document in requirement.documents],
    }


def _document_out(document: RequiredDocument) -> dict[str, Any]:
    return {
        "clause_id": str(document.clause_id),
        "clause_path": document.clause_path,
        "text": document.text,
        #: **The signal to check.** True whenever the item applies only in stated cases.
        "conditional": document.conditional,
        #: The condition phrase, only when it is narrower than the item text itself. Null here does
        #: NOT mean unconditional — `conditional` says that.
        "condition_text": document.condition_text,
        "delegates": document.delegates,
        "has_sub_items": document.has_sub_items,
        "sub_item_paths": list(document.sub_item_paths),
    }


__all__ = ["CAVEAT_MEANING", "router"]
