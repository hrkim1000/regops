"""Tables owned by `regulation` (CLAUDE.md § Table ownership).

Re-exported from the canonical models in ``regops_shared.models`` — never redefined here. A service
that needs to read across the boundary uses raw SQL rather than importing another service's model.

Phase 1.0 covered the L1 subset: the registry, the archive-backed versions, and Tier D metadata.
Phase 1.1 added the clause store — ``clauses``, ``clause_diffs``, ``change_events`` — plus the
``irs`` / ``ir_citations`` shell the diff stage only supersedes. Phase 1.2 fills that shell and adds
``extraction_runs``, ``clause_classifications`` and ``ir_standard_citations``. Phase 2.0a adds the
announcement pair (ADR-0019) — ``amendment_announcements`` and ``announcement_documents``.
"""

from regops_shared.models import (
    IR,
    AmendmentAnnouncement,
    AnnouncementDocument,
    Attachment,
    Cell,
    ChangeEvent,
    Clause,
    ClauseClassification,
    ClauseDiff,
    Document,
    DocumentCell,
    DocumentVersion,
    ExtractionRun,
    FetchObservation,
    IRCitation,
    IRStandardCitation,
    Source,
    SourceDiscoveryRun,
    SourceSchedule,
    StandardReference,
    StructureDriftAlert,
)

__all__ = [
    "IR",
    "AmendmentAnnouncement",
    "AnnouncementDocument",
    "Attachment",
    "Cell",
    "ChangeEvent",
    "Clause",
    "ClauseClassification",
    "ClauseDiff",
    "Document",
    "DocumentCell",
    "DocumentVersion",
    "ExtractionRun",
    "FetchObservation",
    "IRCitation",
    "IRStandardCitation",
    "Source",
    "SourceDiscoveryRun",
    "SourceSchedule",
    "StandardReference",
    "StructureDriftAlert",
]
