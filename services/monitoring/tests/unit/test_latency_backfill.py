"""Detection latency excludes amendments published before the cell came under observation.

Found by the first phase 1.6 gate run. Every alert over the gated corpus carried a publication date
from before ingestion started — 2025-12-30 to 2026-06-09, against a first fetch on 2026-08-03 — so
publication → alert read **5,385 hours** and the gate reported FAIL. Nothing about that number is a
statement of how fast the system detects a change: the change had already happened when the system
arrived.

Two failure directions, and the second is why this cannot be left as a footnote in a report. Today
it fails a system that has not had the chance to be measured. Later, once the backfill ages out of
the window, the same code would report a *pass* without anything about detection having changed.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.api.v1.alerts import _latency
from app.models import Alert
from regops_shared.constants import AlertSeverity

WATCHING_SINCE = datetime(2026, 8, 3, tzinfo=UTC)


def alert(*, published: datetime | None, created: datetime, retrieved: datetime | None = None):
    return Alert(
        id=uuid.uuid4(),
        cell_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_version_id=uuid.uuid4(),
        title="t",
        severity=AlertSeverity.MEDIUM,
        change_event_ids=[],
        published_at=published,
        retrieved_at=retrieved or created,
        detected_at=created,
        created_at=created,
    )


def test_an_amendment_published_before_observation_began_is_counted_apart_not_as_latency():
    backfilled = alert(
        published=datetime(2026, 4, 7, tzinfo=UTC),
        created=datetime(2026, 8, 11, tzinfo=UTC),
    )
    result = _latency([backfilled], WATCHING_SINCE)

    assert result["backfill"] == 1
    assert result["from_published"]["count"] == 0
    assert result["from_published"]["max"] is None
    assert result["watching_since"] == WATCHING_SINCE.isoformat()


def test_an_amendment_published_after_observation_began_is_measured():
    published = WATCHING_SINCE + timedelta(days=10)
    fresh = alert(published=published, created=published + timedelta(hours=6))
    result = _latency([fresh], WATCHING_SINCE)

    assert result["backfill"] == 0
    assert result["from_published"]["count"] == 1
    assert result["from_published"]["max"] == 6.0
    assert result["from_published"]["within_target"] == 1


def test_backfill_does_not_shrink_the_worst_case_of_a_measurable_alert():
    """The exclusion must not become a way to drop an inconvenient number: a slow *measurable*
    alert still sets the maximum, whatever else is in the window."""
    published = WATCHING_SINCE + timedelta(days=1)
    result = _latency(
        [
            alert(
                published=datetime(2026, 1, 1, tzinfo=UTC),
                created=datetime(2026, 8, 11, tzinfo=UTC),
            ),
            alert(published=published, created=published + timedelta(hours=48)),
            alert(published=published, created=published + timedelta(hours=2)),
        ],
        WATCHING_SINCE,
    )

    assert result["backfill"] == 1
    assert result["from_published"]["count"] == 2
    assert result["from_published"]["max"] == 48.0
    assert result["from_published"]["within_target"] == 1


def test_our_own_clock_still_covers_backfill():
    """Retrieval → alert is entirely inside our pipeline, so it bounds us whether or not the
    amendment predates us. Excluding backfill there would discard the only thing measurable."""
    created = datetime(2026, 8, 11, tzinfo=UTC)
    result = _latency(
        [
            alert(
                published=datetime(2026, 1, 1, tzinfo=UTC),
                retrieved=created - timedelta(hours=3),
                created=created,
            )
        ],
        WATCHING_SINCE,
    )
    assert result["from_retrieved"]["count"] == 1
    assert result["from_retrieved"]["max"] == 3.0


def test_an_alert_with_no_publication_date_is_unmeasurable_not_backfill():
    """Different causes, and ADR-0003 decision 5 requires the no-date case be reported as its own
    thing rather than folded into anything else."""
    result = _latency(
        [alert(published=None, created=datetime(2026, 8, 11, tzinfo=UTC))], WATCHING_SINCE
    )
    assert result["unmeasurable"] == 1
    assert result["backfill"] == 0


def test_with_no_observation_history_nothing_is_treated_as_backfill():
    """A cell nobody has fetched yet has no watch start. Guessing one would silently discard every
    alert it has."""
    published = datetime(2026, 1, 1, tzinfo=UTC)
    result = _latency([alert(published=published, created=published + timedelta(hours=5))], None)
    assert result["backfill"] == 0
    assert result["from_published"]["count"] == 1
    assert result["watching_since"] is None
