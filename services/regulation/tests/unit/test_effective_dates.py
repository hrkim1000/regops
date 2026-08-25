"""The effective-date sweep — Part plus date proximity, and null when neither is enough.

The dates here are the ones the live corpus produced on 2026-08-25, because they are what makes the
threshold defensible: every true match sits at **0–2 days** (Parts 803, 860 and 892 at 0, Part 820's
QMSR at 2) and the nearest non-match at **440**. A test that invented its own numbers could not show
that the window sits in a gap two orders of magnitude wide.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.effective_dates import MAX_ABSORPTION_LAG_DAYS, resolve_effective_dates


class _Version:
    """Stands in for a ``DocumentVersion`` row — only the fields the sweep touches."""

    def __init__(self, label: str | None, effective_date: date | None = None) -> None:
        self.id = f"v-{label}"
        self.version_label = label
        self.effective_date = effective_date
        self.effective_date_phrase: str | None = None


class _Announcement:
    def __init__(self, ref: str, effective_on: date | None, phrase: str | None = None) -> None:
        self.ref = ref
        self.effective_on = effective_on
        self.effective_date_phrase = phrase


class _Session:
    """A session double: the sweep only reads versions and their Part's announcements."""

    def __init__(self, pairs, announcements) -> None:
        self._pairs = pairs
        self._announcements = announcements
        self.flushed = False

    def execute(self, _query):
        return _Rows(self._pairs)

    def scalars(self, _query):
        return _Scalars(self._announcements)

    def flush(self) -> None:
        self.flushed = True


class _Rows:
    def __init__(self, pairs) -> None:
        self._pairs = pairs

    def all(self):
        return self._pairs


_EPOCH = date(1, 1, 1)


class _Scalars:
    def __init__(self, items) -> None:
        self._items = items

    def unique(self):
        return self

    def all(self):
        # Mirrors the query's ORDER BY — effective_on descending, then ref. Undated rows sort last
        # rather than being dropped, so the sweep's own guard is what has to reject them.
        def key(a):
            return (0 if a.effective_on else 1, -(a.effective_on or _EPOCH).toordinal(), a.ref)

        return sorted(self._items, key=key)


def _sweep(versions, announcements):
    session = _Session([(v, "doc") for v in versions], announcements)
    return session, resolve_effective_dates(session)


# --- the measured cases ----------------------------------------------------------------------


def test_a_same_day_issue_resolves() -> None:
    """Parts 803, 860 and 892 — the compilation issued the text the day the rule bit."""
    version = _Version("2026-08-06")
    _, summary = _sweep(
        [version],
        [_Announcement("2026-15963", date(2026, 8, 6), "This order is effective August 6, 2026.")],
    )
    assert summary.resolved == 1
    assert version.effective_date == date(2026, 8, 6)
    assert version.effective_date_phrase == "This order is effective August 6, 2026."


def test_the_qmsr_two_day_lag_resolves_to_the_rule_not_the_compilation() -> None:
    """The whole point of ADR-0018 decision 5: 2026-02-02 is the law, 2026-02-04 is the eCFR."""
    version = _Version("2026-02-04")
    _, summary = _sweep([version], [_Announcement("2024-01709", date(2026, 2, 2))])
    assert version.effective_date == date(2026, 2, 2)
    assert summary.resolved == 1


def test_a_440_day_gap_does_not_match() -> None:
    """The nearest non-match in the live corpus. Attaching it would be an invented association."""
    version = _Version("2024-06-03")
    _, summary = _sweep([version], [_Announcement("2023-05657", date(2023, 3, 21))])
    assert version.effective_date is None
    assert summary.unmatched == 1
    assert summary.resolved == 0


def test_the_window_sits_in_the_gap_between_the_two_clusters() -> None:
    """2 days is the widest true match, 440 the nearest false one — the window is not delicate."""
    assert 2 < MAX_ABSORPTION_LAG_DAYS < 440


# --- direction and ordering --------------------------------------------------------------------


def test_a_rule_effective_after_the_issue_date_is_never_matched() -> None:
    """The rule bites, then the compilation absorbs it. The reverse would date a provision by a
    rule that had not yet happened when it was published."""
    version = _Version("2026-02-04")
    _, summary = _sweep([version], [_Announcement("future", date(2033, 3, 7))])
    assert version.effective_date is None
    assert summary.unmatched == 1


def test_the_most_recent_qualifying_rule_wins() -> None:
    """A Part accumulates rules; the one being absorbed is the newest at or before the issue."""
    version = _Version("2026-02-04")
    _sweep(
        [version],
        [
            _Announcement("old", date(2020, 4, 1)),
            _Announcement("recent", date(2026, 2, 2)),
        ],
    )
    assert version.effective_date == date(2026, 2, 2)


def test_a_tie_is_recorded_rather_than_treated_as_a_failure() -> None:
    """The QMSR pair: two rules, one effective date. The *date* is unambiguous either way."""
    version = _Version("2026-02-04")
    _, summary = _sweep(
        [version],
        [
            _Announcement("2024-01709", date(2026, 2, 2), "first"),
            _Announcement("2024-23701", date(2026, 2, 2), "second"),
        ],
    )
    assert version.effective_date == date(2026, 2, 2)
    assert summary.ambiguous == 1
    # Deterministic on ref, so a re-run does not swap the citation's phrase underneath it.
    assert version.effective_date_phrase == "first"


# --- refusing to guess ---------------------------------------------------------------------------


def test_no_announcement_leaves_the_date_null() -> None:
    """ADR-0018 decision 5's fallback is the eCFR ``amendment_date``, which is not persisted.

    Writing the issue date instead would put a value we derived into the column citations resolve
    through — what ADR-0013 forbids. The count is the honest output.
    """
    version = _Version("2024-07-23")
    _, summary = _sweep([version], [])
    assert version.effective_date is None
    assert summary.unmatched == 1


def test_a_rule_without_an_effective_date_is_not_a_candidate() -> None:
    """6 of Part 820's 16 rules state none. They cannot date anything."""
    version = _Version("2026-02-04")
    _, summary = _sweep([version], [_Announcement("undated", None)])
    assert version.effective_date is None


def test_an_unparseable_label_is_counted_never_guessed_at() -> None:
    """An MFDS version carries an MST. There is nothing to measure proximity against."""
    version = _Version("282015")
    _, summary = _sweep([version], [_Announcement("2024-01709", date(2026, 2, 2))])
    assert version.effective_date is None
    assert summary.unlabelled == 1
    assert summary.unmatched == 0


def test_a_missing_label_is_counted_too() -> None:
    version = _Version(None)
    _, summary = _sweep([version], [_Announcement("x", date(2026, 2, 2))])
    assert summary.unlabelled == 1


# --- idempotence ---------------------------------------------------------------------------------


def test_the_sweep_reports_what_it_examined() -> None:
    versions = [_Version("2026-08-06"), _Version("2024-07-23")]
    _, summary = _sweep(versions, [_Announcement("r", date(2026, 8, 6))])
    assert summary.examined == 2
    assert summary.resolved + summary.unmatched + summary.unlabelled == 2


def test_re_running_over_a_resolved_version_does_not_change_it() -> None:
    """Idempotent by construction: the query filters on a null date unless forced."""
    version = _Version("2026-02-04")
    announcements = [_Announcement("2024-01709", date(2026, 2, 2), "phrase")]
    _sweep([version], announcements)
    first = (version.effective_date, version.effective_date_phrase)
    _sweep([version], announcements)
    assert (version.effective_date, version.effective_date_phrase) == first


@pytest.mark.parametrize("lag", [0, 1, 2, MAX_ABSORPTION_LAG_DAYS])
def test_every_lag_inside_the_window_resolves(lag: int) -> None:
    issue = date(2026, 2, 4)
    version = _Version(issue.isoformat())
    _sweep([version], [_Announcement("r", date.fromordinal(issue.toordinal() - lag))])
    assert version.effective_date is not None


def test_one_day_past_the_window_does_not() -> None:
    issue = date(2026, 2, 4)
    version = _Version(issue.isoformat())
    over = date.fromordinal(issue.toordinal() - (MAX_ABSORPTION_LAG_DAYS + 1))
    _sweep([version], [_Announcement("r", over)])
    assert version.effective_date is None
