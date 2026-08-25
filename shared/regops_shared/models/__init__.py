"""Canonical ORM models. Every table is modelled exactly once, here.

The owning service re-exports what it owns (`from regops_shared.models import User`); no service
imports another service's model onto its own metadata.
"""

from regops_shared.models.alert import (
    Alert,
    AlertDelivery,
    AlertSubscription,
    alert_channel_enum,
    alert_severity_enum,
    alert_status_enum,
    delivery_status_enum,
)
from regops_shared.models.announcement import AmendmentAnnouncement, AnnouncementDocument
from regops_shared.models.answer import (
    Answer,
    AnswerCitation,
    ClauseEmbedding,
    Query,
    VerificationResult,
    answer_status_enum,
    embedding_scope_enum,
    verification_verdict_enum,
)
from regops_shared.models.audit import AuditLog
from regops_shared.models.base import Base, TimestampMixin, UUIDPrimaryKey, utcnow
from regops_shared.models.cell import Cell, authority_enum, domain_enum
from regops_shared.models.clause import (
    ChangeEvent,
    Clause,
    ClauseDiff,
    change_kind_enum,
    clause_kind_enum,
)
from regops_shared.models.document import (
    Attachment,
    Document,
    DocumentCell,
    DocumentVersion,
    attachment_kind_enum,
    doc_type_enum,
)
from regops_shared.models.ir import (
    IR,
    ClauseClassification,
    ExtractionRun,
    IRCitation,
    IRStandardCitation,
    classification_kind_enum,
    exclusion_reason_enum,
    extraction_run_status_enum,
    ir_status_enum,
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
    "IR",
    "Alert",
    "AlertDelivery",
    "AlertSubscription",
    "AmendmentAnnouncement",
    "AnnouncementDocument",
    "Answer",
    "AnswerCitation",
    "Attachment",
    "AuditLog",
    "Base",
    "Cell",
    "ChangeEvent",
    "Clause",
    "ClauseClassification",
    "ClauseDiff",
    "ClauseEmbedding",
    "Document",
    "DocumentCell",
    "DocumentVersion",
    "ExtractionRun",
    "FetchObservation",
    "IRCitation",
    "IRStandardCitation",
    "Query",
    "Session",
    "Source",
    "SourceDiscoveryRun",
    "SourceSchedule",
    "StandardReference",
    "StructureDriftAlert",
    "TimestampMixin",
    "UUIDPrimaryKey",
    "User",
    "VerificationResult",
    "alert_channel_enum",
    "alert_severity_enum",
    "alert_status_enum",
    "answer_status_enum",
    "attachment_kind_enum",
    "authority_enum",
    "change_kind_enum",
    "classification_kind_enum",
    "clause_kind_enum",
    "delivery_status_enum",
    "doc_type_enum",
    "domain_enum",
    "drift_signal_enum",
    "embedding_scope_enum",
    "exclusion_reason_enum",
    "extraction_run_status_enum",
    "fetch_outcome_enum",
    "ir_status_enum",
    "role_enum",
    "source_block_enum",
    "source_tier_enum",
    "standard_status_enum",
    "utcnow",
    "verification_verdict_enum",
]
