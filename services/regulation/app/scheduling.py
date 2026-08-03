"""Poll cadence, derived rather than decided per source.

``import-source-map.md`` orders blocks by ingestion priority, so interval is a function of block
plus tier (ADR-0003 decision 4). Adding a source then inherits a sane cadence instead of requiring
a scheduling decision — which is the difference between a catalog that stays current and one where
half the rows were never scheduled because nobody got round to it.

An override is allowed, but ``sources.interval_override_seconds`` and
``interval_override_reason`` are set together and a CHECK constraint enforces it: an override
without a recorded reason is an accident, not a decision.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from regops_shared.constants import (
    POLL_INTERVAL_SECONDS,
    TIER_INTERVAL_FLOOR_SECONDS,
    SourceBlock,
    SourceTier,
)
from regops_shared.models import Source, SourceSchedule
from regops_shared.models.base import utcnow


def derive_interval_seconds(
    block: SourceBlock, tier: SourceTier, *, override_seconds: int | None = None
) -> int:
    """Block sets the cadence; tier sets a floor it cannot go below.

    The floor is what stops a Tier D recognition list inheriting a daily cadence because someone
    filed it under Primary Laws, and what keeps Tier C scraping to at most once a day whatever
    block it sits in.
    """
    if override_seconds is not None:
        return override_seconds
    return max(POLL_INTERVAL_SECONDS[block], TIER_INTERVAL_FLOOR_SECONDS[tier])


def interval_for(source: Source) -> int:
    return derive_interval_seconds(
        source.block, source.tier, override_seconds=source.interval_override_seconds
    )


def advance(schedule: SourceSchedule, *, now: datetime | None = None) -> datetime:
    """Move ``next_due_at`` forward from *now*, not from the previous due time.

    Anchoring on the previous due time makes a source that was down for a day fire a day's worth of
    catch-up polls the moment it recovers — a burst aimed at a host that has just proven fragile.
    """
    moment = now or utcnow()
    schedule.next_due_at = moment + timedelta(seconds=schedule.interval_seconds)
    return schedule.next_due_at


__all__ = ["advance", "derive_interval_seconds", "interval_for"]
