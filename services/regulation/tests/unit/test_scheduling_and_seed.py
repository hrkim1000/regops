"""Cadence is derived from the catalog, and the seed is a faithful projection of it."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.connectors import CONNECTOR_KEYS, GovInfoUSCodeConnector
from app.scheduling import advance, derive_interval_seconds
from app.seed import SEED
from regops_shared.constants import SourceBlock, SourceTier
from regops_shared.models import SourceSchedule

DAY = 24 * 60 * 60


@pytest.mark.parametrize(
    ("block", "tier", "expected"),
    [
        (SourceBlock.PRIMARY_LAWS, SourceTier.A, DAY),
        (SourceBlock.REGULATIONS, SourceTier.A, DAY),
        (SourceBlock.SAFETY, SourceTier.B, DAY),
        (SourceBlock.GUIDANCE, SourceTier.A, 7 * DAY),
        (SourceBlock.OFFICIAL_SOURCES, SourceTier.C, 7 * DAY),
        (SourceBlock.STANDARDS, SourceTier.D, 30 * DAY),
    ],
)
def test_interval_follows_the_block(block: SourceBlock, tier: SourceTier, expected: int) -> None:
    assert derive_interval_seconds(block, tier) == expected


def test_standards_block_is_daily_for_binding_text() -> None:
    """ADR-0003's monthly Standards row is annotated *(Tier D)* and its rationale is about
    metadata. In the MFDS cells the block also holds Tier A 고시 — 화장품 안전기준 등에 관한 규정
    among them — where most of the cosmetic cell's obligations live. Monthly there would miss the
    ≤24h detection-latency gate by a factor of thirty."""
    assert derive_interval_seconds(SourceBlock.STANDARDS, SourceTier.A) == DAY
    assert derive_interval_seconds(SourceBlock.STANDARDS, SourceTier.D) == 30 * DAY


def test_tier_sets_a_floor_the_block_cannot_undercut() -> None:
    """A Tier D row filed under Primary Laws must not inherit a daily cadence, and Tier C scraping
    gets no faster than daily whatever block it sits in."""
    assert derive_interval_seconds(SourceBlock.PRIMARY_LAWS, SourceTier.D) == 30 * DAY
    assert derive_interval_seconds(SourceBlock.SAFETY, SourceTier.C) == DAY


def test_override_wins_but_is_the_only_way_to_deviate() -> None:
    override = derive_interval_seconds(SourceBlock.GUIDANCE, SourceTier.A, override_seconds=3600)
    assert override == 3600


def test_advance_anchors_on_now_not_on_the_missed_due_time() -> None:
    """A source that was down for a day must not fire a day of catch-up polls on recovery."""
    now = datetime(2026, 2, 1, 12, 0, tzinfo=UTC)
    schedule = SourceSchedule(
        source_id=None, interval_seconds=DAY, next_due_at=now - timedelta(days=3)
    )
    assert advance(schedule, now=now) == now + timedelta(seconds=DAY)


# --- the seed ------------------------------------------------------------------


def test_seed_slugs_are_unique() -> None:
    slugs = [row.slug for row in SEED]
    assert len(slugs) == len(set(slugs))


def test_seed_covers_only_cells_something_actually_fetches() -> None:
    """The invariant is not "the gated cells" — it is **no cell nobody fetches**.

    Originally this read ``== {"mfds_samd", "mfds_cosmetic"}`` because Phase 1 gated those two and
    nothing else had a connector. The FDA cells joined on 2026-08-24 when ``ecfr_part`` shipped and
    phase2.0a started, so the set widened — but the reason it exists did not. A seeded cell with
    nothing able to fetch it would put a zero in a coverage denominator and call it a gap.

    EU and NMPA stay out: EU is Phase 4, and NMPA has no connector.
    """
    seeded = {row.cell for row in SEED}
    assert seeded == {"mfds_samd", "mfds_cosmetic", "fda_samd", "fda_cosmetic"}

    fetchable = {row.cell for row in SEED if row.connector is not None}
    assert seeded == fetchable, "a cell is seeded that nothing can fetch"


def test_no_eu_or_nmpa_cell_is_seeded() -> None:
    """EU moved to Phase 4 (2026-08-24) and NMPA is 2.0c — neither has a connector to fetch with."""
    for row in SEED:
        assert not row.cell.startswith(("eu_", "nmpa_")), f"{row.slug}: cell is not built yet"


def test_every_seeded_connector_exists() -> None:
    for row in SEED:
        if row.connector is not None:
            assert row.connector in CONNECTOR_KEYS, f"{row.slug}: unknown connector"


def test_rows_without_a_connector_are_not_ingestible() -> None:
    for row in SEED:
        if row.connector is None:
            assert not row.ingestible, f"{row.slug}: ingestible but nothing can fetch it"


def test_unverified_endpoints_are_seeded_disabled() -> None:
    """Firing guessed URLs at a government host to discover their shape is the wrong way to learn.
    The row and its connector exist; the schedule does not run until W3 recon confirms it."""
    for row in SEED:
        if row.notes and "unverified" in row.notes.lower():
            assert row.enabled is False, f"{row.slug}: unverified endpoint must not be scheduled"


def test_every_interval_override_carries_a_reason() -> None:
    """An override without a recorded reason is an accident, not a decision. The dataclass rejects
    it and a CHECK constraint on ``sources`` backs that up at the database."""
    for row in SEED:
        assert (row.interval_override_seconds is None) == (row.interval_override_reason is None)


#: Connectors that may serve a ``PRIMARY_LAWS`` row, per authority.
#:
#: Three now, not two. The set is authority-shaped because a primary law *is*: 국가법령정보 serves
#: 현행 and 시행예정 as two endpoints (ADR-0016), while the FD&C Act reaches us as a USC
#: chapter from govinfo (ADR-0018 decision 12). This is what would catch a primary-law row
#: wired to a feed or a standards connector, so it is widened deliberately rather than dropped.
_PRIMARY_LAW_CONNECTORS = {"law_go_kr_law", "law_go_kr_eflaw", "govinfo_uscode"}


def test_primary_law_sources_are_enabled() -> None:
    """The 국가법령정보 본문조회 endpoints are the ones the spike confirmed, and they are the
    ingestion path for both gated cells.

    Two connectors for MFDS, not one: every 법령 has a ``law_go_kr_eflaw`` companion tracking its
    시행예정 amendments (ADR-0016). Both are enabled, because detection latency for the 법령 sources
    is unmeasurable without the second.

    The FDA cells add a third: the FD&C Act, one Document claimed by both of them.
    """
    primary = [row for row in SEED if row.block is SourceBlock.PRIMARY_LAWS]
    assert len(primary) >= 6
    assert all(row.enabled for row in primary)
    assert all(row.connector in _PRIMARY_LAW_CONNECTORS for row in primary)


def test_the_fdc_act_is_one_document_claimed_by_both_fda_cells() -> None:
    """Both FDA cells seed the statute, and both rows resolve to the same ``canonical_key``.

    This is the M:N case phase 2.0a exists to exercise, and the assertion that matters is the
    *identity*, not the row count: two rows carrying different params would quietly create two
    Documents for one Act, which is the duplicate ADR-0002 decision 1 exists to prevent. The MFDS
    RSS boards already work this way; this is the first instrument to.
    """
    rows = [row for row in SEED if row.connector == "govinfo_uscode"]
    assert {row.cell for row in rows} == {"fda_samd", "fda_cosmetic"}

    connector = GovInfoUSCodeConnector()
    keys = {connector.canonical_key(row.params["title"], row.params["chapter"]) for row in rows}
    assert keys == {"fda:usc:21-9"}


def test_every_law_has_a_pending_effect_companion() -> None:
    """Polling 현행 only makes an amendment invisible between 공포 and 시행 — 2 months to 2.4 years
    for the gated 법령, so the ≤24h gate is structurally unmeetable without an eflaw source per law
    (ADR-0016)."""
    current = {row.params["name"] for row in SEED if row.connector == "law_go_kr_law"}
    pending = {row.params["name"] for row in SEED if row.connector == "law_go_kr_eflaw"}
    assert current == pending, f"법령 without a 시행예정 companion: {sorted(current - pending)}"


# --- the M:N case Phase 1 otherwise lacks --------------------------------------


def test_both_cells_claim_the_same_mfds_boards() -> None:
    """MFDS boards are regulator-wide: 제개정고시등 announces 식품, 의약품, 의료기기 and 화장품
    alike. Both gated cells therefore subscribe to the same upstream board, which is the real M:N
    case — and the one the synthetic fan-out fixture in phase 1.1 stands in for."""
    boards: dict[str, set[str]] = {}
    for row in SEED:
        if row.connector == "mfds_rss":
            boards.setdefault(row.params["brdId"], set()).add(row.cell)

    shared = {brd for brd, cells in boards.items() if len(cells) > 1}
    assert shared, "no board is shared, so the M:N path is untested"
    for brd in shared:
        assert boards[brd] == {"mfds_cosmetic", "mfds_samd"}


def test_shared_boards_resolve_to_one_document_identity() -> None:
    """Identity comes from the authority's board id, not our source slug. Keyed on the slug, one
    feed would become one Document per cell — the duplicate ADR-0002 decision 1 exists to prevent
    — and each cell would archive and version the same bytes separately."""
    from app.connectors.base import SourceSpec
    from app.connectors.mfds import MfdsRssConnector

    connector = MfdsRssConnector()
    specs = [
        SourceSpec(
            slug=row.slug,
            title=row.title,
            tier=row.tier,
            ingestible=True,
            url_template=row.url_template,
            params=row.params,
        )
        for row in SEED
        if row.connector == "mfds_rss" and row.params.get("brdId") == "data0008"
    ]
    assert len(specs) == 2, "data0008 should be claimed by both cells"
    assert len({connector.identity(spec) for spec in specs}) == 1
    assert connector.identity(specs[0]) == "data0008"


def test_no_fetchable_source_is_disabled_without_a_recorded_reason() -> None:
    """The invariant is not "nothing fetchable is off" — it is **nothing is off silently**.

    This read ``assert row.enabled`` for every row with a connector, and the reason given was that
    after the W3 reconnaissance nothing fetchable was left switched off. That held while the only
    two states were "we can fetch it" and "there is nothing to fetch it with". A third arrived on
    2026-08-25: a source whose connector works and whose **authority refuses us** — FDA's CDN
    answers our identified agent with an abuse-detection redirect.

    A row in that state must not fire, and must say why. Turning one off quietly is the failure
    this guard exists to catch, and it is unchanged.
    """
    for row in SEED:
        if row.connector is not None and not row.enabled:
            assert row.notes, f"{row.slug} is disabled with no reason recorded"
            assert len(row.notes) > 40, f"{row.slug}: the reason is too terse to act on"
