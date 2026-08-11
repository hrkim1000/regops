"""The day boundary — the one thing ``version_status`` explicitly defers to this phase.

``regops_shared.constants.version_status`` evaluates the effective-date boundary in UTC and says so:
a Korean date reads as pending for nine hours after it takes effect in Korea, which is harmless on a
browser label and wrong on a briefing whose entire subject is *when* something changed.

So briefing timestamps are rendered in the authority's own timezone, and the window is a rolling 24
hours rather than a calendar day — a subscriber may hold cells across authorities in different
timezones, and a calendar-day window would need a boundary that is wrong for at least one of them.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.briefing import local_timestamp
from regops_shared.constants import Authority


def test_a_korean_amendment_is_shown_in_korean_time() -> None:
    """23:30 UTC on the 10th is 08:30 KST on the 11th — a different day to the person reading it."""
    moment = datetime(2026, 8, 10, 23, 30, tzinfo=UTC)

    rendered = local_timestamp(moment, Authority.MFDS.value)

    assert rendered.startswith("2026-08-11T08:30")
    assert rendered.endswith("+09:00")


def test_each_authority_renders_in_its_own_zone() -> None:
    moment = datetime(2026, 8, 10, 23, 30, tzinfo=UTC)

    korean = local_timestamp(moment, Authority.MFDS.value)
    american = local_timestamp(moment, Authority.FDA.value)

    assert korean != american
    assert american.startswith("2026-08-10T19:30")


def test_an_unmapped_authority_falls_back_rather_than_raising() -> None:
    """A wrong-looking timestamp beats a briefing that 500s. All four in scope are mapped."""
    moment = datetime(2026, 8, 10, 23, 30, tzinfo=UTC)

    assert local_timestamp(moment, "") == moment.isoformat()
