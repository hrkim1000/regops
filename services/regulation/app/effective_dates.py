"""Resolve a CFR version's legally stated effective date from the rule that announced it.

[ADR-0018](../../../docs/design/ADR-0018-fda-source-model.md) decision 5 wants the Federal
Register's ``effective_on`` in preference to the eCFR's own date.
[ADR-0019](../../../docs/design/ADR-0019-announced-amendments.md) decision 5 deliberately did not
perform that join, and its open question 1 asked *where* it belongs. **A sweep, after the fact** —
not at version-write time — because a rule can be published *after* the eCFR issues the text it
explains, so a join done once at write time would be permanently wrong for those and a sweep simply
resolves them on its next run.

**The match is Part plus date proximity, never a citation string.** The eCFR sources Part 820 to
``89 FR 7523`` while the Federal Register calls the same rule ``89 FR 7496`` — 7523 is a page
*inside* it — so the strings do not join (ADR-0018 decision 4). The Part comes from
``announcement_documents``; the proximity is below.

**Direction is fixed: the rule bites, then the compilation absorbs it.** So a candidate must satisfy
``0 <= issue_date - effective_on``. A rule effective *after* the text was issued cannot have caused
it, and admitting one would attach next year's date to this year's provision.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from regops_shared.constants import DocType
from regops_shared.models import (
    AmendmentAnnouncement,
    AnnouncementDocument,
    Document,
    DocumentVersion,
)

log = structlog.get_logger(__name__)

#: How far the compilation may lag the rule and still be the same event, in days.
#:
#: **Measured, not chosen.** Across the 13 in-scope Parts on 2026-08-25 the gaps fall in two
#: clusters with nothing between them: every true match is **0–2 days** (Parts 803, 860 and 892 at
#: 0; Part 820's QMSR at 2), and the nearest non-match is **440 days**. The threshold sits in a gap
#: two orders of magnitude wide, so its exact value is not load-bearing — 30 tolerates a compilation
#: that lags some weeks without coming near the noise.
#:
#: If a future measurement puts a real match beyond this, widen it *and* say so here. Silently
#: raising a matching window is how a join starts inventing associations.
MAX_ABSORPTION_LAG_DAYS = 30


@dataclass(slots=True)
class SweepSummary:
    """What one sweep did. Counts, because the interesting number is what stayed unresolved."""

    examined: int = 0
    resolved: int = 0
    #: A version whose Part has announcements, none of them within the window.
    unmatched: int = 0
    #: More than one rule shares the winning date — the QMSR pair does. Not an error: the *date* is
    #: unambiguous even when the rule is not, and it is recorded so the count stays explicable.
    ambiguous: int = 0
    #: ``version_label`` did not parse as a date, so there was nothing to measure proximity against.
    unlabelled: int = 0
    resolved_ids: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "examined": self.examined,
            "resolved": self.resolved,
            "unmatched": self.unmatched,
            "ambiguous": self.ambiguous,
            "unlabelled": self.unlabelled,
        }


def _issue_date(version: DocumentVersion) -> date | None:
    """The eCFR issue date this version was fetched at, from its label.

    Parsed defensively rather than assumed: ``version_label`` is whatever the connector put there,
    and an MFDS version carries an MST. A label that is not a date is counted, never guessed at.
    """
    if not version.version_label:
        return None
    try:
        return date.fromisoformat(version.version_label)
    except ValueError:
        return None


def _best_match(
    session: Session, *, document_id: object, issued_on: date
) -> tuple[AmendmentAnnouncement | None, int]:
    """The announcement whose ``effective_on`` best explains this issue date, and how many tied.

    Ordering is ``effective_on`` descending — the most recent rule at or before the issue date is
    the one the compilation was absorbing. Ties are broken on ``ref`` so a re-run resolves the same
    way; a citation that changed between runs would be worse than one that is merely imprecise.
    """
    candidates = (
        session.scalars(
            select(AmendmentAnnouncement)
            .join(
                AnnouncementDocument,
                AnnouncementDocument.announcement_id == AmendmentAnnouncement.id,
            )
            .where(
                AnnouncementDocument.document_id == document_id,
                AmendmentAnnouncement.effective_on.is_not(None),
                AmendmentAnnouncement.effective_on <= issued_on,
            )
            .order_by(
                AmendmentAnnouncement.effective_on.desc(),
                AmendmentAnnouncement.ref,
            )
        )
        .unique()
        .all()
    )
    for announcement in candidates:
        # The query already excludes these two, and they are re-checked here on purpose: both are
        # *correctness* rules rather than filters — a rule with no date cannot date anything, and a
        # rule effective after the text was issued cannot have caused it. Leaving them only in SQL
        # would put the rules where a unit test cannot reach them.
        if announcement.effective_on is None or announcement.effective_on > issued_on:
            continue
        if (issued_on - announcement.effective_on).days > MAX_ABSORPTION_LAG_DAYS:
            # Ordered by date descending, so once one is too old every later one is too.
            break
        tied = sum(1 for c in candidates if c.effective_on == announcement.effective_on)
        return announcement, tied
    return None, 0


def resolve_effective_dates(session: Session, *, force: bool = False) -> SweepSummary:
    """Fill ``effective_date`` on regulation versions that do not have one yet.

    Only ``DocType.REGULATION`` versions are examined — the doc_type, never the authority, which is
    the same rule profile selection follows (ADR-0002 decision 3).

    Idempotent. A version that already carries a date is skipped unless ``force``, so the sweep can
    run after every ingest without rewriting settled citations. **An unmatched version stays null**:
    ADR-0018 decision 5 names the eCFR ``amendment_date`` as the fallback, and that value is not
    persisted anywhere today, so inventing one here would put a date we derived into the column
    citations resolve through — precisely what ADR-0013 forbids. The count is the honest output.
    """
    summary = SweepSummary()
    query = (
        select(DocumentVersion, Document.id)
        .join(Document, Document.id == DocumentVersion.document_id)
        .where(Document.doc_type == DocType.REGULATION)
    )
    if not force:
        query = query.where(DocumentVersion.effective_date.is_(None))

    for version, document_id in session.execute(query).all():
        summary.examined += 1
        issued_on = _issue_date(version)
        if issued_on is None:
            summary.unlabelled += 1
            continue

        announcement, tied = _best_match(session, document_id=document_id, issued_on=issued_on)
        if announcement is None:
            summary.unmatched += 1
            continue

        version.effective_date = announcement.effective_on
        version.effective_date_phrase = announcement.effective_date_phrase
        summary.resolved += 1
        summary.resolved_ids.append(str(version.id))
        if tied > 1:
            summary.ambiguous += 1
        log.info(
            "effective_date.resolved",
            document_version=str(version.id),
            issued_on=issued_on.isoformat(),
            effective_on=announcement.effective_on.isoformat()
            if announcement.effective_on
            else None,
            announcement=announcement.ref,
            lag_days=(issued_on - announcement.effective_on).days
            if announcement.effective_on
            else None,
            tied=tied,
        )

    session.flush()
    log.info("effective_date.sweep", **summary.as_dict())
    return summary


__all__ = ["MAX_ABSORPTION_LAG_DAYS", "SweepSummary", "resolve_effective_dates"]
