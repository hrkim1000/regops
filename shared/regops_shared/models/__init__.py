"""Canonical ORM models. Every table is modelled exactly once, here.

The owning service re-exports what it owns (`from regops_shared.models import User`); no service
imports another service's model onto its own metadata.
"""

from regops_shared.models.audit import AuditLog
from regops_shared.models.base import Base, TimestampMixin, UUIDPrimaryKey, utcnow
from regops_shared.models.cell import Cell, authority_enum, domain_enum
from regops_shared.models.document import (
    Attachment,
    Document,
    DocumentCell,
    DocumentVersion,
    attachment_kind_enum,
    doc_type_enum,
)
from regops_shared.models.source import (
    FetchObservation,
    Source,
    SourceDiscoveryRun,
    SourceSchedule,
    StructureDriftAlert,
    drift_signal_enum,
    fetch_outcome_enum,
    source_block_enum,
    source_tier_enum,
)
from regops_shared.models.standard import StandardReference, standard_status_enum
from regops_shared.models.user import Session, User, role_enum

__all__ = [
    "Attachment",
    "AuditLog",
    "Base",
    "Cell",
    "Document",
    "DocumentCell",
    "DocumentVersion",
    "FetchObservation",
    "Session",
    "Source",
    "SourceDiscoveryRun",
    "SourceSchedule",
    "StandardReference",
    "StructureDriftAlert",
    "TimestampMixin",
    "UUIDPrimaryKey",
    "User",
    "attachment_kind_enum",
    "authority_enum",
    "doc_type_enum",
    "domain_enum",
    "drift_signal_enum",
    "fetch_outcome_enum",
    "role_enum",
    "source_block_enum",
    "source_tier_enum",
    "standard_status_enum",
    "utcnow",
]
