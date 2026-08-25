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

#: 시행일법령 목록 — amendments already 공포'd but not yet in force. This is a **list** endpoint:
#: ``lawService.do?target=eflaw`` has no 본문조회 and answers HTTP 500, so the connector reads this
#: list and fetches each pending MST through the ordinary 법령 endpoint (ADR-0016).
EFLAW_SEARCH = (
    "https://www.law.go.kr/DRF/lawSearch.do?OC={OC}&target=eflaw&type=XML&display=100&query={name}"
)


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


def _eflaw(cell: str, ordinal: int, name: str, title: str) -> SeedSource:
    """A 시행예정 companion to a 법령 source, tracking the same instrument before it is in force.

    Separate source rather than an extra mode on the 법령 connector: it polls a different endpoint,
    and its own ``fetch_observations`` are what make "we checked for pending amendments at T" an
    auditable fact — which is the whole basis of the detection-coverage measurement.

    The versions it yields attach to the **same** Document as 현행, because both resolve to the same
    법령ID (ADR-0016 decision 1).
    """
    return SeedSource(
        cell=cell,
        block=SourceBlock.PRIMARY_LAWS,
        ordinal=ordinal,
        name=f"{name}_pending",
        title=f"{title} (시행예정)",
        tier=SourceTier.A,
        connector="law_go_kr_eflaw",
        url_template=EFLAW_SEARCH,
        params={"name": title},
        notes=(
            "시행예정 법령 — detection latency for the 법령 sources is unmeasurable without this, "
            "because an amendment is invisible between 공포 and 시행 (ADR-0016)."
        ),
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


def _cfr_part(
    cell: str,
    ordinal: int,
    part: str,
    title: str,
    *,
    block: SourceBlock = SourceBlock.REGULATIONS,
    notes: str | None = None,
) -> SeedSource:
    """One CFR Part — one Document (ADR-0018 decision 1), fetched by the ``ecfr_part`` connector.

    No ``url_template``: this connector composes both of its endpoints from ``title`` and ``part``
    rather than from a template, because the body URL carries a date the connector does not know
    until the versions endpoint has answered. A template with a ``{date}`` placeholder nothing could
    fill would be a lie about where the URL comes from.
    """
    return SeedSource(
        cell=cell,
        block=block,
        ordinal=ordinal,
        name=f"cfr_{part.replace('.', '_')}",
        title=title,
        tier=SourceTier.A,
        connector="ecfr_part",
        params={"title": "21", "part": part},
        notes=notes,
    )


def _fr_part(cell: str, ordinal: int, part: str, subject: str) -> SeedSource:
    """The Federal Register feed for one CFR Part — dates and identifiers, no regulation text.

    Paired with the ``_cfr_part`` row of the same Part so the join ADR-0018 decision 5 needs is
    structural: ``fda:fr:21-820`` against ``fda:cfr:21-820``. The eCFR sources that Part to
    ``89 FR 7523`` while the Federal Register calls the same rule ``89 FR 7496``, so citation
    strings cannot be joined on and the Part is what is left to join by.

    Block is ``SAFETY`` regardless of where the Part itself sits: this is a change-signal surface,
    like the MFDS RSS boards, not the instrument.
    """
    return SeedSource(
        cell=cell,
        block=SourceBlock.SAFETY,
        ordinal=ordinal,
        name=f"fr_{part}",
        title=f"Federal Register — final rules affecting 21 CFR Part {part} ({subject})",
        tier=SourceTier.A,
        connector="federal_register",
        params={"title": "21", "part": part},
    )


#: Header labels the FDA Recognized Consensus Standards table uses, mapped onto ``StandardRecord``.
#: Configuration rather than code (ADR-0003 decision 7's shape): an FDA table and an MFDS 인정 목록
#: are the same shape with different labels. Whitespace is folded at match time, so these name the
#: column rather than reproducing the page's line breaks.
#:
#: Two fields this surface cannot fill, and no configuration can: ``edition`` has no column of its
#: own — FDA folds it into the designation, "62304 Edition 1.1 2015-06 CONSOLIDATED VERSION" — and
#: ``withdrawal_date`` is absent from the list view entirely.
FDA_STANDARD_COLUMNS: dict[str, tuple[str, ...]] = {
    "number": ("standard designation number and date",),
    "issuing_body": ("standards developing organization",),
    "recognition_number": ("recognition number",),
    "title": ("standard title (click for recognition information)", "standard title"),
    "effective_date": ("date of entry",),
}

#: The recognition list is queried per standard rather than swept. The connector fetches one page
#: and does not follow the pager, and the whole list runs past 1,000 rows over 10+ pages — but
#: ``import-source-map.md`` names six standards for the FDA cells, and each returns one or two rows
#: on a single page. Sweeping the list would fetch 1,000 records to keep 8.
FDA_RECOGNISED_STANDARDS: tuple[tuple[str, str], ...] = (
    ("62304", "IEC 62304 — medical device software life cycle"),
    ("14971", "ISO 14971 — risk management"),
    ("62366", "IEC 62366-1 — usability engineering"),
    ("81001-5-1", "IEC 81001-5-1 — health software security"),
    ("SW96", "ANSI/AAMI SW96 — medical device security risk management"),
    ("CR515", "AAMI CR515 — software bill of materials"),
)


def _recognition(ordinal: int, reference: str, title: str) -> SeedSource:
    """One recognised standard's *record*, from the list. The standard itself is never fetched.

    Tier **B**, not D: the recognition list is an ingestible page and this row fetches only it.
    The Tier D rows are the standards themselves, which have no connector and no fetch path at all
    (ADR-0003 decision 7).
    """
    return SeedSource(
        cell="fda_samd",
        block=SourceBlock.STANDARDS,
        ordinal=ordinal,
        name=f"recognition_{reference.lower().replace('-', '_')}",
        title=f"FDA Recognized Consensus Standards — {title}",
        tier=SourceTier.B,
        connector="recognition_list",
        url_template=(
            "https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfStandards/"
            "results.cfm?referencenumber={reference}&Search=Search"
        ),
        params={"reference": reference, "columns": FDA_STANDARD_COLUMNS},
        #: **Disabled: FDA's CDN classifies our agent as abuse** (2026-08-25). accessdata.fda.gov
        #: sits behind Akamai, which answers this identified client with a 302 to
        #: ``/apology_objects/abuse-detection-apology.html`` — a page that is itself 404. The
        #: parser and the column mapping are verified against the live page and produce correct
        #: records; only the fetch is refused.
        #:
        #: The row exists and does not fire, which is this file's rule for an endpoint we cannot
        #: reach. **Finding a User-Agent that slips through would be evasion**, and it is the
        #: behaviour ADR-0018 decision 11 forbids on the other FDA hosts for the same reason. The
        #: way forward is to ask FDA for access, not to look less like ourselves.
        enabled=False,
        notes="Metadata only. The recognition list is fetched; the standard is not, and "
        "standard_references has no column its text could occupy. "
        "Schedule disabled 2026-08-25: Akamai abuse-detection refuses our agent — see phase2.0a "
        "Deviations 17. Re-enable when access is granted, not by changing how we identify.",
    )


SEED: tuple[SeedSource, ...] = (
    # --- mfds_cosmetic ------------------------------------------------------
    _law("mfds_cosmetic", 1, "cosmetics_act", "화장품법"),
    _law("mfds_cosmetic", 2, "cosmetics_act_decree", "화장품법 시행령"),
    _law("mfds_cosmetic", 3, "cosmetics_act_rule", "화장품법 시행규칙"),
    _eflaw("mfds_cosmetic", 11, "cosmetics_act", "화장품법"),
    _eflaw("mfds_cosmetic", 12, "cosmetics_act_decree", "화장품법 시행령"),
    _eflaw("mfds_cosmetic", 13, "cosmetics_act_rule", "화장품법 시행규칙"),
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
    _eflaw("mfds_samd", 11, "medical_device_act", "의료기기법"),
    _eflaw("mfds_samd", 12, "medical_device_act_decree", "의료기기법 시행령"),
    _eflaw("mfds_samd", 13, "medical_device_act_rule", "의료기기법 시행규칙"),
    _eflaw("mfds_samd", 14, "digital_medical_products_act", "디지털의료제품법"),
    _eflaw("mfds_samd", 15, "digital_medical_products_act_decree", "디지털의료제품법 시행령"),
    _eflaw("mfds_samd", 16, "digital_medical_products_act_rule", "디지털의료제품법 시행규칙"),
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
    # --- fda_samd -----------------------------------------------------------
    #
    # The 13 CFR Parts import-source-map.md names for the two FDA cells, every one confirmed
    # present and unreserved against the eCFR structure endpoint on 2026-08-24. The FD&C Act
    # (govinfo) and the Federal Register are **not** here: the act needs its version identity
    # settled (ADR-0018 open question 7) and the Federal Register connector does not exist yet.
    _cfr_part("fda_samd", 1, "820", "21 CFR Part 820 — Quality Management System Regulation"),
    _cfr_part("fda_samd", 2, "892", "21 CFR Part 892 — Radiology Devices"),
    _cfr_part("fda_samd", 3, "860", "21 CFR Part 860 — Medical Device Classification Procedures"),
    _cfr_part("fda_samd", 4, "11", "21 CFR Part 11 — Electronic Records; Electronic Signatures"),
    _cfr_part("fda_samd", 5, "803", "21 CFR Part 803 — Medical Device Reporting"),
    _cfr_part("fda_samd", 6, "806", "21 CFR Part 806 — Reports of Corrections and Removals"),
    _cfr_part(
        "fda_samd",
        7,
        "807",
        "21 CFR Part 807 — Establishment Registration and Device Listing",
        block=SourceBlock.REGISTRATION,
    ),
    _cfr_part(
        "fda_samd",
        8,
        "822",
        "21 CFR Part 822 — Postmarket Surveillance",
        block=SourceBlock.SAFETY,
    ),
    _cfr_part(
        "fda_samd",
        9,
        "7",
        "21 CFR Part 7 — Enforcement Policy",
        block=SourceBlock.SAFETY,
    ),
    # --- fda_cosmetic -------------------------------------------------------
    _cfr_part("fda_cosmetic", 1, "700", "21 CFR Part 700 — Cosmetics, General"),
    _cfr_part("fda_cosmetic", 2, "701", "21 CFR Part 701 — Cosmetic Labeling"),
    _cfr_part(
        "fda_cosmetic",
        3,
        "740",
        "21 CFR Part 740 — Cosmetic Product Warning Statements",
    ),
    _cfr_part(
        "fda_cosmetic",
        4,
        "710",
        "21 CFR Part 710 — Voluntary Registration of Cosmetic Product Establishments",
        block=SourceBlock.REGISTRATION,
        notes="Title is the authority's own and is out of step with the statute: MoCRA made "
        "facility registration mandatory while this Part still says voluntary. Which one the cell "
        "treats as authoritative is ADR-0018 open question 5 — a scope decision, not a connector "
        "one. Seeded because the Part is live and unreserved; the title is not ours to correct.",
    ),
    # --- Federal Register, one feed per Part --------------------------------
    #
    # The effective date the eCFR does not carry, and the only view of an amendment that is
    # published but not yet in force — the eCFR 404s on future dates (ADR-0018 decisions 5 and 7).
    _fr_part("fda_samd", 11, "820", "QMSR"),
    _fr_part("fda_samd", 12, "892", "radiology devices"),
    _fr_part("fda_samd", 13, "860", "classification procedures"),
    _fr_part("fda_samd", 14, "11", "electronic records"),
    _fr_part("fda_samd", 15, "803", "medical device reporting"),
    _fr_part("fda_samd", 16, "806", "corrections and removals"),
    _fr_part("fda_samd", 17, "807", "establishment registration"),
    _fr_part("fda_samd", 18, "822", "postmarket surveillance"),
    _fr_part("fda_samd", 19, "7", "enforcement policy"),
    _fr_part("fda_cosmetic", 11, "700", "cosmetics general"),
    _fr_part("fda_cosmetic", 12, "701", "cosmetic labeling"),
    _fr_part("fda_cosmetic", 13, "740", "warning statements"),
    _fr_part("fda_cosmetic", 14, "710", "establishment registration"),
    # --- fda_samd standards — Tier D metadata via the recognition list ------
    *(
        _recognition(i, reference, title)
        for i, (reference, title) in enumerate(FDA_RECOGNISED_STANDARDS, start=1)
    ),
)

#: 행정규칙 added from the discovery sweep on 2026-08-06 — the triage backlog, decided in.
#:
#: Keyed on the authority's own **행정규칙ID**, not a hand-invented English name. 53 slugs
#: invented by us would drift from the Korean title they stand for and would join to nothing;
#: the ID is stable, is what `mfds-admrul-coverage.md` prints, and cannot be transcribed
#: wrong. The curated sources above predate the sweep and keep their names.
#:
#: A 고시 claimed by both cells is seeded **twice**, one row per cell — the shape the RSS
#: boards already use. Both resolve to one 행정규칙ID and so to one Document claimed by two
#: cells (ADR-0002 decision 1).
SWEPT_ADMRUL: tuple[tuple[str, str, str], ...] = (
    ("mfds_cosmetic", "36121", "기능성화장품 기준 및 시험방법"),
    ("mfds_cosmetic", "74525", "맞춤형화장품판매업자의 준수사항에 관한 규정"),
    ("mfds_cosmetic", "36497", "수입화장품 품질검사 면제에 관한 규정"),
    (
        "mfds_cosmetic",
        "73120",
        "영유아 또는 어린이 사용 화장품 안전성 자료의 작성·보관에 관한 규정",
    ),
    ("mfds_cosmetic", "33248", "우수화장품 제조 및 품질관리기준"),
    ("mfds_cosmetic", "33326", "의약품등의 타르색소 지정과 기준 및 시험방법"),
    ("mfds_cosmetic", "41823", "화장품 가격표시제 실시요령"),
    ("mfds_cosmetic", "34091", "화장품 바코드 표시 및 관리요령"),
    ("mfds_cosmetic", "37973", "화장품 사용할 때의 주의사항 및 알레르기 유발성분 표시에 관한 규정"),
    ("mfds_cosmetic", "38375", "화장품 안전성 정보관리 규정"),
    (
        "mfds_cosmetic",
        "72508",
        "화장품 원료 사용금지 해제·변경 및 사용기준 지정·변경 심사에 관한 규정",
    ),
    ("mfds_cosmetic", "38705", "화장품의 색소 종류 및 기준"),
    ("mfds_cosmetic", "41380", "화장품의 생산ㆍ수입실적 및 원료목록 보고에 관한 규정"),
    ("mfds_cosmetic", "36123", "인체적용제품의 위해성평가에 관한 규정"),
    ("mfds_samd", "36123", "인체적용제품의 위해성평가에 관한 규정"),
    (
        "mfds_samd",
        "53694",
        "(식품의약품안전처) 의료기기 허가·신의료기술평가 등 통합운영에 관한 규정",
    ),
    ("mfds_samd", "92690", "디지털의료기기 임상시험등 계획 승인 및 실시·관리에 관한 규정"),
    ("mfds_samd", "92728", "디지털의료기기 전자적 침해행위 보안 지침"),
    ("mfds_samd", "92664", "디지털의료기기 제조 및 품질관리 기준"),
    ("mfds_samd", "92541", "디지털의료제품 분류 및 등급 지정 등에 관한 규정"),
    ("mfds_samd", "92599", "디지털의료제품 허가·인증·신고·심사 및 평가 등에 관한 규정"),
    ("mfds_samd", "92310", "디지털의료제품법에 따른 기관 지정 등에 관한 규정"),
    ("mfds_samd", "77343", "생산·수입 중단 보고대상 의료기기 및 보고 방법"),
    ("mfds_samd", "37100", "의료기기 기술문서심사기관 지정 및 운영 등에 관한 규정"),
    ("mfds_samd", "36140", "의료기기 부작용 등 안전성 정보 관리에 관한 규정"),
    ("mfds_samd", "33364", "의료기기 생산 및 수출·수입·수리실적 보고에 관한 규정"),
    ("mfds_samd", "63745", "의료기기 수입요건확인 면제 등에 관한 규정"),
    ("mfds_samd", "36522", "의료기기 시판 후 조사에 관한 규정"),
    ("mfds_samd", "49294", "의료기기 위탁 인증·신고의 대상 및 범위 등에 관한 지침"),
    ("mfds_samd", "79578", "의료기기 이물 보고대상 및 절차 등에 관한 규정"),
    ("mfds_samd", "37970", "의료기기 임상시험 기본문서 관리에 관한 규정"),
    ("mfds_samd", "33367", "의료기기 임상시험계획 승인에 관한 규정"),
    ("mfds_samd", "2052526", "의료기기 임상시험기관 지정에 관한 규정"),
    ("mfds_samd", "33373", "의료기기 재평가에 관한 규정"),
    ("mfds_samd", "97658", "의료기기 제조 및 품질관리 관련 기관 지정 등에 관한 규정"),
    ("mfds_samd", "77644", "의료기기 제조허가등 갱신에 관한 규정"),
    ("mfds_samd", "67874", "의료기기 통합정보 관리 등에 관한 규정"),
    ("mfds_samd", "41266", "의료기기 표시·기재 등에 관한 규정"),
    ("mfds_samd", "66058", "의료기기 표준코드의 표시 및 관리요령"),
    ("mfds_samd", "32269", "의료기기 품목 및 품목별 등급에 관한 규정"),
    ("mfds_samd", "78039", "의료기기 회수·폐기 등에 관한 규정"),
    ("mfds_samd", "72348", "의료기기소프트웨어제조기업 인증제도 운영에 관한 규정"),
    ("mfds_samd", "32061", "의료기기의 생물학적 안전에 관한 공통기준규격"),
    ("mfds_samd", "41382", "의료기기의 안정성시험 기준"),
    ("mfds_samd", "33365", "의료기기의 전기·기계적 안전에 관한 공통기준규격"),
    ("mfds_samd", "32062", "의료기기의 전자파안전에 관한 공통기준규격"),
    ("mfds_samd", "67388", "인터넷 홈페이지 형태 첨부문서 제공 가능 의료기기의 지정에 관한 규정"),
    ("mfds_samd", "93660", "장기추적조사대상 의료기기 지정 및 실사용 정보 제출에 관한 규정"),
    ("mfds_samd", "46294", "추적관리대상 의료기기 기록과 자료 제출에 관한 규정"),
    ("mfds_samd", "33378", "추적관리대상 의료기기 지정에 관한 규정"),
    ("mfds_samd", "72347", "혁신의료기기 기술 및 관리기준 표준화에 관한 규정"),
    ("mfds_samd", "72346", "혁신의료기기 지정 절차 및 방법 등에 관한 규정"),
    ("mfds_samd", "76476", "혁신의료기기 허가 등에 관한 특례 규정"),
    ("mfds_samd", "70675", "희소·긴급도입 필요 의료기기 공급 등에 관한 규정"),
)


def _swept(cell: str, admrul_id: str, title: str, ordinal: int) -> SeedSource:
    """One row of :data:`SWEPT_ADMRUL` as a seed source.

    Block is ``REGULATIONS`` for every swept 고시 — they impose duties, and for Tier A that block
    polls daily exactly as STANDARDS, REGISTRATION and SAFETY do. Refining a row into a narrower
    block changes ordering, not behaviour, so it is not worth guessing 53 times.
    """
    return SeedSource(
        cell=cell,
        block=SourceBlock.REGULATIONS,
        ordinal=ordinal,
        name=f"admrul_{admrul_id}",
        title=title,
        tier=SourceTier.A,
        connector="law_go_kr_admrul",
        url_template=ADMRUL_SERVICE,
        params={"name": title},
        notes=f"행정규칙ID {admrul_id}. Added from the discovery sweep, 2026-08-06.",
    )


SEED = SEED + tuple(
    _swept(cell, admrul_id, title, 100 + index)
    for index, (cell, admrul_id, title) in enumerate(SWEPT_ADMRUL)
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
            # Re-derive the interval so a catalog reclassification takes effect.
            schedule.interval_seconds = interval_for(source)
            # **The catalog may stop a schedule; it may never start one.** Leaving `enabled`
            # untouched altogether protected the operator who disabled a drifting source
            # deliberately — and made a seed-level disable inert, which is worse than surprising:
            # a row the catalog says must not fire keeps firing. Disabling is the safe direction,
            # so it propagates; enabling is the one that would override a deliberate stop, so it
            # never does.
            if not (row.enabled and row.ingestible and bool(row.connector)):
                schedule.enabled = False
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
