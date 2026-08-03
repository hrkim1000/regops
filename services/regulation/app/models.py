"""Tables owned by `regulation` (CLAUDE.md § Table ownership).

Re-exported from the canonical models in ``regops_shared.models`` — never redefined here. A service
that needs to read across the boundary uses raw SQL rather than importing another service's model.

Phase 1.0 covers the L1 subset: the registry, the archive-backed versions, and Tier D metadata.
``clauses``, ``clause_diffs`` and ``change_events`` arrive with phase 1.1.
"""

from regops_shared.models import (
    Attachment,
    Cell,
    Document,
    DocumentCell,
    DocumentVersion,
    FetchObservation,
    Source,
    SourceDiscoveryRun,
    SourceSchedule,
    StandardReference,
    StructureDriftAlert,
)

__all__ = [
    "Attachment",
    "Cell",
    "Document",
    "DocumentCell",
    "DocumentVersion",
    "FetchObservation",
    "Source",
    "SourceDiscoveryRun",
    "SourceSchedule",
    "StandardReference",
    "StructureDriftAlert",
]
