"""Tables owned by `regulation` (CLAUDE.md § Table ownership).

Re-exported from the canonical models in ``regops_shared.models`` — never redefined here. A service
that needs to read across the boundary uses raw SQL rather than importing another service's model.

Phase 1.0 covered the L1 subset: the registry, the archive-backed versions, and Tier D metadata.
Phase 1.1 adds the clause store — ``clauses``, ``clause_diffs``, ``change_events`` — plus the
``irs`` / ``ir_citations`` shell that phase 1.2 fills and the diff stage only supersedes.
"""

from regops_shared.models import (
    IR,
    Attachment,
    Cell,
    ChangeEvent,
    Clause,
    ClauseDiff,
    Document,
    DocumentCell,
    DocumentVersion,
    FetchObservation,
    IRCitation,
    Source,
    SourceDiscoveryRun,
    SourceSchedule,
    StandardReference,
    StructureDriftAlert,
)

__all__ = [
    "IR",
    "Attachment",
    "Cell",
    "ChangeEvent",
    "Clause",
    "ClauseDiff",
    "Document",
    "DocumentCell",
    "DocumentVersion",
    "FetchObservation",
    "IRCitation",
    "Source",
    "SourceDiscoveryRun",
    "SourceSchedule",
    "StandardReference",
    "StructureDriftAlert",
]
