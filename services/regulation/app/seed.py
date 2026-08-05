"""Seed the source registry for the two gated cells.

[docs/import-source-map.md](../../../docs/import-source-map.md) stays the single catalog. This
module is its **runtime projection**, not a second list: the rows below carry only what a connector
needs to reach a source — the catalog's own title, block and ordering — and nothing about scope,
priority or coverage that the map does not already state. When the two disagree, the map is right
and this file is stale.

Two things are deliberately absent:

- **No credential.** ``url_template`` carries ``{OC}``; the key lives in settings and is resolved at
  request time (ADR-0003 decision 13).
- **No hand-set interval.** Cadence is derived from block + tier at seed time
  (:mod:`app.scheduling`), so a row added here inherits one rather than needing a decision.

**Sources whose URL is unverified are seeded with the schedule disabled.** The connector for them is
built and unit-tested against fixtures; what is missing is a confirmed endpoint, and firing guessed
URLs at a government host to find out is the wrong way to learn. Enable them once the W3
reconnaissance confirms the shape — that is a plan item, not a code change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from regops_shared.constants import SourceBlock, SourceTier
from regops_shared.models import Cell, Source, SourceSchedule
from regops_shared.models.base import utcnow

from .scheduling import interval_for

log = structlog.get_logger(__name__)

#: 국가법령정보 본문조회. ``LM`` queries by 법령명 / 행정규칙명, which is what the catalog gives us;
#: the document's identity still comes from the 법령ID the response returns, so querying by name
#: does not weaken ``canonical_key``.
LAW_SERVICE = "https://www.law.go.kr/DRF/lawService.do?OC={OC}&target=law&LM={name}&type=XML"

#: MFDS publishes each board as RSS. Boards mapped live 2026-08-05 by fetching all 35 feeds and
#: reading the channel title each declares — guessing from the directory page's link text does not
#: work, because every link shares one generic title attribute.
MFDS_RSS = "https://www.mfds.go.kr/www/rss/brd.do?brdId={brdId}"
ADMRUL_SERVICE = "https://www.law.go.kr/DRF/lawService.do?OC={OC}&target=admrul&LM={name}&type=XML"


@dataclass(frozen=True, slots=True)
class SeedSource:
    cell: str
    block: SourceBlock
    ordinal: int
    name: str
    title: str
    tier: SourceTier
    ingestible: bool = True
    connector: str | None = None
    url_template: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    #: False where the endpoint is not yet confirmed. The row exists; it just does not fire.
    enabled: bool = True
    notes: str | None = None
    #: Set together or not at all — an override without a recorded reason is an accident, and a
    #: CHECK constraint on ``sources`` enforces the pairing.
    interval_override_seconds: int | None = None
    interval_override_reason: str | None = None

    def __post_init__(self) -> None:
        if (self.interval_override_seconds is None) != (self.interval_override_reason is None):
            raise ValueError(f"{self.slug}: an interval override must carry a reason")

    @property
    def slug(self) -> str:
        return f"{self.cell}.{self.block.value}.{self.name}"


def _law(cell: str, ordinal: int, name: str, title: str) -> SeedSource:
    return SeedSource(
        cell=cell,
        block=SourceBlock.PRIMARY_LAWS,
        ordinal=ordinal,
        name=name,
        title=title,
        tier=SourceTier.A,
        connector="law_go_kr_law",
        url_template=LAW_SERVICE,
        params={"name": title},
    )


def _admrul(cell: str, block: SourceBlock, ordinal: int, name: str, title: str) -> SeedSource:
    return SeedSource(
        cell=cell,
        block=block,
        ordinal=ordinal,
        name=name,
        title=title,
        tier=SourceTier.A,
        connector="law_go_kr_admrul",
        url_template=ADMRUL_SERVICE,
        params={"name": title},
    )


SEED: tuple[SeedSource, ...] = (
    # --- mfds_cosmetic ------------------------------------------------------
    _law("mfds_cosmetic", 1, "cosmetics_act", "화장품법"),
    _law("mfds_cosmetic", 2, "cosmetics_act_decree", "화장품법 시행령"),
    _law("mfds_cosmetic", 3, "cosmetics_act_rule", "화장품법 시행규칙"),
    # 별표 1 (사용할 수 없는 원료) and 별표 2 (사용상의 제한이 필요한 원료) live here. They arrive
    # inline as <별표단위>/<별표내용> and become child Documents that version on their own
    # (ADR-0012) — which is what stops an ingredient-list amendment being missed.
    _admrul(
        "mfds_cosmetic",
        SourceBlock.STANDARDS,
        1,
        "cosmetic_safety_standards",
        "화장품 안전기준 등에 관한 규정",
    ),
    _admrul(
        "mfds_cosmetic",
        SourceBlock.STANDARDS,
        2,
        "functional_cosmetics_review",
        "기능성화장품 심사에 관한 규정",
    ),
    _admrul(
        "mfds_cosmetic",
        SourceBlock.STANDARDS,
        3,
        "labelling_advertising",
        "화장품 표시·광고 실증에 관한 규정",
    ),
    SeedSource(
        cell="mfds_cosmetic",
        block=SourceBlock.SAFETY,
        ordinal=1,
        name="rss_amendments",
        title="MFDS RSS — 제개정고시등",
        tier=SourceTier.B,
        connector="mfds_rss",
        url_template=MFDS_RSS,
        params={"brdId": "data0008"},
        notes="Confirmed live 2026-08-05. Supersedes the HTML 제개정고시등 scrape: the same "
        "board is published as RSS, with a pubDate per item and no 조회수 to strip.",
    ),
    SeedSource(
        cell="mfds_cosmetic",
        block=SourceBlock.SAFETY,
        ordinal=2,
        name="rss_statutes",
        title="MFDS RSS — 법, 시행령, 시행규칙",
        tier=SourceTier.B,
        connector="mfds_rss",
        url_template=MFDS_RSS,
        params={"brdId": "data0003"},
        notes="Announces 법령 amendments; the 법령 본문조회 connector fetches the text itself.",
    ),
    SeedSource(
        cell="mfds_cosmetic",
        block=SourceBlock.SAFETY,
        ordinal=3,
        name="rss_preannounce",
        title="MFDS RSS — 입법/행정예고",
        tier=SourceTier.B,
        connector="mfds_rss",
        url_template=MFDS_RSS,
        params={"brdId": "data0009"},
        notes="Pre-announcement: change visible before promulgation, which is earlier than "
        "any 본문 poll can see it.",
    ),
    SeedSource(
        cell="mfds_cosmetic",
        block=SourceBlock.OFFICIAL_SOURCES,
        ordinal=1,
        name="mfds_portal",
        title="https://www.mfds.go.kr",
        tier=SourceTier.C,
        ingestible=False,
        enabled=False,
        notes="Navigation surface, not content. Reference only — no connector attached.",
    ),
    # --- mfds_samd ----------------------------------------------------------
    _law("mfds_samd", 1, "medical_device_act", "의료기기법"),
    _law("mfds_samd", 2, "medical_device_act_decree", "의료기기법 시행령"),
    _law("mfds_samd", 3, "medical_device_act_rule", "의료기기법 시행규칙"),
    # A 법률 with its own 시행령 and 시행규칙, exactly parallel to the two acts above — which is
    # why all three sit in Primary Laws. The catalog previously listed the act alone, under
    # Regulations; corrected 2026-08-03 (법령ID 014601 / 014826 / 014846, verified live).
    _law("mfds_samd", 4, "digital_medical_products_act", "디지털의료제품법"),
    _law("mfds_samd", 5, "digital_medical_products_act_decree", "디지털의료제품법 시행령"),
    _law("mfds_samd", 6, "digital_medical_products_act_rule", "디지털의료제품법 시행규칙"),
    _admrul(
        "mfds_samd",
        SourceBlock.REGULATIONS,
        1,
        "device_approval_review",
        "의료기기 허가·신고·심사 등에 관한 규정",
    ),
    _admrul(
        "mfds_samd",
        SourceBlock.REGULATIONS,
        2,
        "device_gmp",
        "의료기기 제조 및 품질관리 기준",
    ),
    _admrul(
        "mfds_samd",
        SourceBlock.REGULATIONS,
        3,
        "device_standards",
        "의료기기 기준규격",
    ),
    # Tier D. No connector, no url_template, ingestible=false — there is no code path from this
    # row to stored body text, and standard_references has no column that could hold it.
    SeedSource(
        cell="mfds_samd",
        block=SourceBlock.STANDARDS,
        ordinal=1,
        name="iec_62304_recognition",
        title="IEC 62304 관련 인정 표준 — 메타데이터만 (Tier D)",
        tier=SourceTier.D,
        ingestible=False,
        enabled=False,
        notes="Tier D. Freshness is tracked through the recognition list "
        "(mfds_samd.standards.recognition_list), never by fetching the standard.",
    ),
    SeedSource(
        cell="mfds_samd",
        block=SourceBlock.SAFETY,
        ordinal=1,
        name="rss_amendments",
        title="MFDS RSS — 제개정고시등",
        tier=SourceTier.B,
        connector="mfds_rss",
        url_template=MFDS_RSS,
        params={"brdId": "data0008"},
        notes="Same upstream board as the cosmetic cell claims — one Document, claimed by "
        "both (ADR-0002 decision 1). This is the M:N case Phase 1 otherwise lacks.",
    ),
    SeedSource(
        cell="mfds_samd",
        block=SourceBlock.SAFETY,
        ordinal=2,
        name="rss_statutes",
        title="MFDS RSS — 법, 시행령, 시행규칙",
        tier=SourceTier.B,
        connector="mfds_rss",
        url_template=MFDS_RSS,
        params={"brdId": "data0003"},
        notes="Shared board; see the cosmetic cell.",
    ),
    SeedSource(
        cell="mfds_samd",
        block=SourceBlock.SAFETY,
        ordinal=3,
        name="rss_preannounce",
        title="MFDS RSS — 입법/행정예고",
        tier=SourceTier.B,
        connector="mfds_rss",
        url_template=MFDS_RSS,
        params={"brdId": "data0009"},
        notes="Shared board; see the cosmetic cell.",
    ),
    SeedSource(
        cell="mfds_samd",
        block=SourceBlock.SAFETY,
        ordinal=4,
        name="rss_device_sanctions",
        title="MFDS RSS — 의료기기 행정처분",
        tier=SourceTier.B,
        connector="mfds_rss",
        url_template=MFDS_RSS,
        params={"brdId": "plc0168"},
        notes="SaMD-specific safety board.",
    ),
    SeedSource(
        cell="mfds_samd",
        block=SourceBlock.OFFICIAL_SOURCES,
        ordinal=1,
        name="emedi_portal",
        title="https://emedi.mfds.go.kr",
        tier=SourceTier.C,
        ingestible=False,
        enabled=False,
        notes="Navigation surface, not content. Reference only — no connector attached.",
    ),
)


def seed_sources(session: Session, *, seed: tuple[SeedSource, ...] = SEED) -> dict[str, int]:
    """Upsert the catalog projection. Idempotent — safe to re-run after the map changes."""
    cells = {cell.slug: cell.id for cell in session.scalars(select(Cell)).all()}
    created = updated = 0

    for row in seed:
        cell_id = cells.get(row.cell)
        if cell_id is None:  # pragma: no cover - the 8 cells are seeded by migration 0001
            raise ValueError(f"{row.slug}: unknown cell {row.cell!r}")

        source = session.scalar(select(Source).where(Source.slug == row.slug))
        if source is None:
            source = Source(slug=row.slug, cell_id=cell_id)
            session.add(source)
            created += 1
        else:
            updated += 1

        source.block = row.block
        source.ordinal = row.ordinal
        source.title = row.title
        source.url_template = row.url_template
        source.tier = row.tier
        source.ingestible = row.ingestible
        source.connector = row.connector
        source.params = dict(row.params)
        source.notes = row.notes
        source.interval_override_seconds = row.interval_override_seconds
        source.interval_override_reason = row.interval_override_reason
        session.flush()

        schedule = session.get(SourceSchedule, source.id)
        if schedule is None:
            schedule = SourceSchedule(
                source_id=source.id,
                interval_seconds=interval_for(source),
                next_due_at=utcnow(),
                enabled=row.enabled and row.ingestible and bool(row.connector),
            )
            session.add(schedule)
        else:
            # Re-derive the interval so a catalog reclassification takes effect, but leave
            # `enabled` alone: an operator may have disabled a drifting source deliberately.
            schedule.interval_seconds = interval_for(source)
        session.flush()

    # A source dropped from the catalog must stop polling. Disable rather than delete: documents
    # reference the source that discovered them, and deleting would either fail on the foreign key
    # or destroy that provenance. Re-seeding is upsert-only otherwise, so without this a row
    # removed from the map keeps fetching forever and nothing says why.
    known = {row.slug for row in seed}
    retired = 0
    for source in session.scalars(select(Source).where(Source.slug.not_in(known))).all():
        schedule = session.get(SourceSchedule, source.id)
        if schedule is not None and schedule.enabled:
            schedule.enabled = False
            retired += 1
        source.notes = (
            "Retired: no longer in import-source-map.md. Schedule disabled by the seeder."
        )
    session.flush()

    session.commit()
    log.info("seed.sources", created=created, updated=updated, retired=retired, total=len(seed))
    return {"created": created, "updated": updated, "retired": retired, "total": len(seed)}


__all__ = ["SEED", "SeedSource", "seed_sources"]
