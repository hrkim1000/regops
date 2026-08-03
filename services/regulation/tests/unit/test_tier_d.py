"""Tier D is structural, not a policy someone has to remember.

Four independent places have to hold, and this file checks each:

1. ``standard_references`` has no ``text`` column and no varchar over 512 — there is physically
   nowhere for a standard's body text to go (ADR-0002 decision 2).
2. Every connector refuses a Tier D or non-ingestible source at its entry point.
3. The recognition-list connector returns metadata and **no artefacts**, so nothing on the Tier D
   path can reach the WORM archive.
4. The seeded Tier D row carries no connector and no URL.

The CI string scan (``scripts/tier_d_scan.py``) is the backstop for the case where all four fail.
It is not the mechanism.
"""

from __future__ import annotations

import pytest
from helpers import StubFetcher, fixture_bytes
from sqlalchemy import String

from app.connectors import RecognitionListConnector, get_connector
from app.connectors.base import NonIngestibleSourceError, SourceSpec, assert_ingestible
from app.seed import SEED
from regops_shared.constants import SourceTier, StandardStatus
from regops_shared.models import StandardReference
from regops_shared.models.standard import MAX_METADATA_LENGTH

TIER_D_SPEC = SourceSpec(
    slug="mfds_samd.standards.iec_62304_recognition",
    title="IEC 62304 관련 인정 표준",
    tier=SourceTier.D,
    ingestible=False,
    url_template=None,
)


# --- 1. nowhere to put the text ------------------------------------------------


def test_standard_references_has_no_unbounded_text_column() -> None:
    """``Text`` subclasses ``String`` with ``length is None``, so one check catches both."""
    unbounded = [
        column.name
        for column in StandardReference.__table__.columns
        if isinstance(column.type, String) and column.type.length is None
    ]
    assert unbounded == [], (
        f"{unbounded} could hold a standard's body text. Tier D is enforced by the absence of "
        "somewhere to put it — add a bounded varchar or a typed column instead."
    )


def test_every_standard_reference_string_column_is_bounded_and_short() -> None:
    for column in StandardReference.__table__.columns:
        if isinstance(column.type, String):
            assert column.type.length is not None, f"{column.name} is unbounded"
            assert column.type.length <= MAX_METADATA_LENGTH, (
                f"{column.name} is {column.type.length} chars — long enough to start holding "
                "content rather than a recognition record"
            )


def test_standard_reference_carries_only_the_recognition_record() -> None:
    """The permitted fields, stated positively so a future addition is a deliberate act."""
    permitted = {
        "id",
        "number",
        "edition",
        "issuing_body",
        "recognition_number",
        "title",
        "effective_date",
        "withdrawal_date",
        "status",
        "official_url",
        "cell_id",
        "source_id",
        "last_seen_at",
        "created_at",
        "updated_at",
    }
    actual = {c.name for c in StandardReference.__table__.columns}
    assert actual == permitted, f"unexpected columns: {actual ^ permitted}"


# --- 2. no fetch path ----------------------------------------------------------


def test_tier_d_source_is_refused_at_the_connector_boundary() -> None:
    with pytest.raises(NonIngestibleSourceError, match="Tier D"):
        assert_ingestible(TIER_D_SPEC)


def test_non_ingestible_source_is_refused_even_at_a_collectable_tier() -> None:
    """Login-gated portals are Tier C but still unfetchable by construction."""
    portal = SourceSpec(
        slug="mfds_cosmetic.official_sources.mfds_portal",
        title="portal",
        tier=SourceTier.C,
        ingestible=False,
        url_template="https://example.invalid",
    )
    with pytest.raises(NonIngestibleSourceError):
        assert_ingestible(portal)


@pytest.mark.parametrize(
    "connector_key", ["law_go_kr_law", "law_go_kr_admrul", "mfds_rss", "mfds_listing"]
)
def test_no_connector_will_fetch_a_tier_d_source(connector_key: str) -> None:
    connector = get_connector(connector_key, fetcher=StubFetcher(body=b"<r/>"))
    with pytest.raises(NonIngestibleSourceError):
        connector.fetch(TIER_D_SPEC)


# --- 3. the recognition list yields metadata only ------------------------------


def test_recognition_list_returns_records_and_no_artifacts() -> None:
    """Freshness is tracked through the list, which is Tier B and ingestible. The standard it
    names is never fetched, and there is no bytes field on the way out."""
    spec = SourceSpec(
        slug="mfds_samd.standards.recognition_list",
        title="의료기기 인정 표준 목록",
        tier=SourceTier.B,
        ingestible=True,
        url_template="https://example.invalid/list",
    )
    stub = StubFetcher(body=fixture_bytes("recognition_list.html"), content_type="text/html")
    result = RecognitionListConnector(fetcher=stub).fetch(spec)

    assert result.artifacts == (), "a Tier D path must not produce anything archivable"
    assert len(result.standards) == 3

    by_number = {record.number: record for record in result.standards}
    assert by_number["IEC 62304"].edition == "2015"
    assert by_number["IEC 62304"].recognition_number == "MFDS-2026-011"
    assert by_number["IEC 62304"].status == StandardStatus.RECOGNIZED.value
    assert by_number["IEC 62366-1"].status == StandardStatus.WITHDRAWN.value
    assert by_number["ISO 14971"].official_url.startswith("https://")

    for record in result.standards:
        assert not hasattr(record, "body")
        assert not hasattr(record, "text")


# --- 4. the seed ---------------------------------------------------------------


def test_seeded_tier_d_rows_have_no_fetch_path() -> None:
    tier_d = [row for row in SEED if row.tier is SourceTier.D]
    assert tier_d, "the mfds_samd Standards block includes a Tier D row"
    for row in tier_d:
        assert row.ingestible is False
        assert row.connector is None
        assert row.url_template is None
