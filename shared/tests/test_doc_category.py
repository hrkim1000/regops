"""Which rung of the legal ladder a document sits on — from `doc_type` plus, for an annex, the
*parent's*.

Worth its own test because the annex case is the whole reason the function takes two arguments:
별표 of a 법령 and 별표 of a 고시 are **different categories**, and the annex row carries
``doc_type = 'annex'`` for both. A one-argument version would silently collapse 219 법령 별표 and
239 행정규칙 별표 into one bucket.
"""

from __future__ import annotations

import pytest

from regops_shared.constants import DOC_CATEGORY_ORDER, DocCategory, DocType, doc_category


@pytest.mark.parametrize("doc_type", ["law", "decree", "enforcement_rule", "codified_statute"])
def test_every_enacted_instrument_is_one_category(doc_type: str) -> None:
    """법률 · 시행령 · 시행규칙 · U.S.C. are one bucket, however we type them.

    ``codified_statute`` belongs here because a U.S.C. chapter *is* a statute — rearranged by
    subject, which is a publishing format and not a different rung (ADR-0018 decision 12).
    """
    assert doc_category(doc_type) is DocCategory.STATUTE


@pytest.mark.parametrize("doc_type", ["notice", "regulation"])
def test_a_delegated_rule_is_an_admin_rule_whichever_authority_issued_it(doc_type: str) -> None:
    """고시 and a C.F.R. Part are counterparts: an agency issuing rules under delegated power.

    This is the pair that had to be decided. Mapping ``regulation`` onto ``STATUTE`` would have put
    21 C.F.R. Part 700 beside the FD&C Act as though Congress had passed it.
    """
    assert doc_category(doc_type) is DocCategory.ADMIN_RULE


def test_an_annex_is_categorised_by_its_parent() -> None:
    assert doc_category("annex", "notice") is DocCategory.ADMIN_RULE_ANNEX
    assert doc_category("annex", "law") is DocCategory.STATUTE_ANNEX
    assert doc_category("annex", "enforcement_rule") is DocCategory.STATUTE_ANNEX
    # A C.F.R. appendix follows its Part down, with no branch of its own.
    assert doc_category("annex", "regulation") is DocCategory.ADMIN_RULE_ANNEX
    assert doc_category("annex", "codified_statute") is DocCategory.STATUTE_ANNEX


def test_an_annex_with_no_parent_falls_back_to_statute_rather_than_vanishing() -> None:
    """A parentless annex should not exist — a CHECK constraint forbids it — but if one appears the
    category must still be a real bucket, or the row drops out of every grouped view."""
    assert doc_category("annex", None) is DocCategory.STATUTE_ANNEX


def test_a_feed_is_not_a_holding() -> None:
    """An RSS board is a change signal, not an instrument. It gets its own bucket so it is neither
    counted as a holding nor silently dropped."""
    assert doc_category("feed") is DocCategory.FEED


def test_an_unknown_type_is_other_not_an_exception() -> None:
    """A new `doc_type` must not break a listing before anyone has decided where it belongs."""
    assert doc_category("something_new") is DocCategory.OTHER


def test_every_doc_type_maps_to_a_category() -> None:
    """No `DocType` may fall through — a document with no category is invisible when grouped."""
    for doc_type in DocType:
        parent = "notice" if doc_type is DocType.ANNEX else None
        assert doc_category(doc_type.value, parent) in DOC_CATEGORY_ORDER


def test_no_storable_doc_type_lands_in_other() -> None:
    """``other`` means *unclassified*, and the test above cannot tell that apart from *uncovered* —
    ``OTHER`` is a member of ``DOC_CATEGORY_ORDER``, so a fall-through satisfies it.

    That is not hypothetical. ``regulation`` and ``codified_statute`` were added for the FDA cells
    and both fell through for weeks: every FDA document displayed as 기타 while the suite stayed
    green. This is the assertion that would have caught it, and the one that catches the next type.

    ``guidance`` is the sole exemption, and by decision rather than omission: ADR-0021 keeps
    nonbinding text out of ``documents`` entirely, so no guidance row exists to be grouped.
    """
    unclassified = {
        doc_type.value
        for doc_type in DocType
        if doc_category(doc_type.value, "notice" if doc_type is DocType.ANNEX else None)
        is DocCategory.OTHER
    }
    assert unclassified == {DocType.GUIDANCE.value}


def test_the_display_order_covers_every_category() -> None:
    """The UI renders in this order and drops anything missing from it."""
    assert set(DOC_CATEGORY_ORDER) == set(DocCategory)
    assert DOC_CATEGORY_ORDER.index(DocCategory.STATUTE) < DOC_CATEGORY_ORDER.index(
        DocCategory.ADMIN_RULE
    )
    assert DOC_CATEGORY_ORDER.index(DocCategory.ADMIN_RULE) < DOC_CATEGORY_ORDER.index(
        DocCategory.STATUTE_ANNEX
    )


# --- version status (ADR-0016 decision 6) ------------------------------------------------


def test_in_force_is_the_latest_date_that_has_arrived() -> None:
    from datetime import date

    from regops_shared.constants import in_force_date

    today = date(2026, 8, 6)
    assert in_force_date([date(2025, 1, 1), date(2026, 4, 2)], today=today) == date(2026, 4, 2)
    # A future date must never be chosen just because it is the newest.
    assert in_force_date([date(2026, 4, 2), date(2026, 12, 31)], today=today) == date(2026, 4, 2)


def test_nothing_in_force_is_a_real_state_not_a_fallback_to_the_newest() -> None:
    """An instrument whose every version is still pending has no in-force text, and saying it does
    would answer "what applies today" with a rule nobody is bound by yet."""
    from datetime import date

    from regops_shared.constants import in_force_date

    assert in_force_date([date(2027, 1, 1), date(2028, 1, 1)], today=date(2026, 8, 6)) is None
    assert in_force_date([None, None], today=date(2026, 8, 6)) is None


def test_status_matches_the_live_shape_of_the_cosmetics_act() -> None:
    """화장품법 on 2026-08-06: one 시행중 and four 시행예정."""
    from datetime import date

    from regops_shared.constants import VersionStatus, in_force_date, version_status

    today = date(2026, 8, 6)
    dates = [
        date(2026, 4, 2),  # 현행
        date(2026, 10, 8),
        date(2026, 11, 27),
        date(2026, 12, 31),
        date(2027, 4, 29),
    ]
    in_force = in_force_date(dates, today=today)
    statuses = [version_status(d, in_force=in_force, today=today) for d in dates]

    assert statuses[0] is VersionStatus.IN_FORCE
    assert all(s is VersionStatus.PENDING for s in statuses[1:])


def test_an_older_arrived_version_is_superseded_not_in_force() -> None:
    """Two dates in the past: only the later one is in force. Calling both 시행중 would let a
    stale version be cited as current."""
    from datetime import date

    from regops_shared.constants import VersionStatus, in_force_date, version_status

    today = date(2026, 8, 6)
    dates = [date(2025, 1, 1), date(2026, 4, 2)]
    in_force = in_force_date(dates, today=today)

    assert version_status(dates[0], in_force=in_force, today=today) is VersionStatus.SUPERSEDED
    assert version_status(dates[1], in_force=in_force, today=today) is VersionStatus.IN_FORCE


def test_a_null_effective_date_is_unknown_never_in_force() -> None:
    """ADR-0013 keeps the date null when 부칙 states a condition. Treating that as in force would
    put an unresolved version forward as the current text."""
    from datetime import date

    from regops_shared.constants import VersionStatus, version_status

    assert (
        version_status(None, in_force=date(2026, 4, 2), today=date(2026, 8, 6))
        is VersionStatus.UNKNOWN
    )


def test_a_version_effective_today_is_in_force_not_pending() -> None:
    """The boundary case, and the one a `>` vs `>=` slip gets wrong."""
    from datetime import date

    from regops_shared.constants import VersionStatus, in_force_date, version_status

    today = date(2026, 8, 6)
    in_force = in_force_date([today], today=today)
    assert version_status(today, in_force=in_force, today=today) is VersionStatus.IN_FORCE
