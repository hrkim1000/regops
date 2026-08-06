"""Shared constants. No magic literals in service code."""

from collections.abc import Iterable
from datetime import date
from enum import StrEnum
from typing import Final


class Authority(StrEnum):
    """The only four regulatory authorities in scope (CLAUDE.md § Architecture rules)."""

    MFDS = "mfds"
    FDA = "fda"
    EU = "eu"
    NMPA = "nmpa"


class Domain(StrEnum):
    """The only two product domains in scope."""

    SAMD = "samd"
    COSMETIC = "cosmetic"


#: Exactly 8 cells. ``Authority`` x ``Domain`` is the complete coverage target; the UNIQUE
#: constraint on (authority, domain) plus these two enums make a 9th row structurally impossible.
CELLS: Final[tuple[tuple[Authority, Domain], ...]] = tuple(
    (authority, domain) for authority in Authority for domain in Domain
)

CELL_COUNT: Final[int] = 8


class Role(StrEnum):
    """Phase 1 RBAC (ADR-0005 decision 5). ``compliance`` arrives in Phase 2."""

    VIEWER = "viewer"
    RA = "ra"
    ADMIN = "admin"


#: Ordered least- to most-privileged; each role subsumes the ones before it.
ROLE_ORDER: Final[tuple[Role, ...]] = (Role.VIEWER, Role.RA, Role.ADMIN)


class SourceTier(StrEnum):
    """Source collectability. Tier D source text is never ingested."""

    A = "a"  # public API
    B = "b"  # static files / RSS
    C = "c"  # scraping
    D = "d"  # copyright-protected — metadata only, never body text


class SourceBlock(StrEnum):
    """Subsection of a cell in ``docs/import-source-map.md``.

    Block order *is* ingestion priority: ``PRIMARY_LAWS`` first, ``OFFICIAL_SOURCES`` last.
    Poll interval is derived from this plus tier — see ``POLL_INTERVAL_SECONDS``.
    """

    PRIMARY_LAWS = "primary_laws"
    REGULATIONS = "regulations"
    STANDARDS = "standards"
    GUIDANCE = "guidance"
    REGISTRATION = "registration"
    INGREDIENT = "ingredient"
    GMP = "gmp"
    SAFETY = "safety"
    OFFICIAL_SOURCES = "official_sources"


_DAY: Final[int] = 24 * 60 * 60

#: Poll interval per block (ADR-0003 decision 4). Derived, never hand-set per source: adding a
#: source inherits a sane cadence instead of requiring a scheduling decision. A source may override
#: it, but only with a reason recorded on the source row.
#:
#: ``STANDARDS`` is daily here, where ADR-0003's table says monthly. That row of the table is
#: annotated *(Tier D)* and its rationale is "metadata only — recognition lists move slowly", so
#: monthly is a property of the tier, not of the block. It moved to the tier floor below. In the
#: MFDS cells the ``Standards`` block holds Tier A 고시 — 화장품 안전기준 등에 관한 규정 among them,
#: which carries most of the cosmetic cell's obligations in its 별표. Polling those monthly would
#: miss the ≤24h detection-latency gate by a factor of thirty on the cell's most important content.
POLL_INTERVAL_SECONDS: Final[dict[SourceBlock, int]] = {
    SourceBlock.PRIMARY_LAWS: _DAY,  # where legal change actually lands
    SourceBlock.REGULATIONS: _DAY,
    SourceBlock.REGISTRATION: _DAY,
    SourceBlock.INGREDIENT: _DAY,  # annexes and amending acts
    SourceBlock.STANDARDS: _DAY,  # binding 고시 unless the tier floor says otherwise
    SourceBlock.GMP: 7 * _DAY,
    SourceBlock.SAFETY: _DAY,  # time-sensitive by nature
    SourceBlock.GUIDANCE: 7 * _DAY,  # changes a few times a year
    SourceBlock.OFFICIAL_SOURCES: 7 * _DAY,  # navigation surfaces, not content
}

#: Floor per tier, applied after the block. Tier D is metadata-only and its recognition list moves
#: slowly, so it is monthly whatever block someone files it under. Tier C is scraped and gets no
#: faster than daily for the same reason.
TIER_INTERVAL_FLOOR_SECONDS: Final[dict[SourceTier, int]] = {
    SourceTier.A: 0,
    SourceTier.B: 0,
    SourceTier.C: _DAY,
    SourceTier.D: 30 * _DAY,
}


class DocType(StrEnum):
    """What kind of instrument a Document is. Domain-neutral (ADR-0002 decision 3)."""

    LAW = "law"  # 법률
    DECREE = "decree"  # 시행령
    ENFORCEMENT_RULE = "enforcement_rule"  # 시행규칙
    NOTICE = "notice"  # 고시 / 행정규칙
    ANNEX = "annex"  # 별표 — versions independently of its parent (ADR-0012)
    GUIDANCE = "guidance"
    FEED = "feed"  # RSS / listing surface


class DocCategory(StrEnum):
    """The authority's own top-level taxonomy, which is how an RA already thinks about the corpus.

    국가법령정보 groups its holdings as 현행법령 · 현행 행정규칙 · 법령 별표·서식 · 행정규칙
    별표·서식 (and 법령해석, which RegOps does not ingest). Grouping the browser this way rather
    than by our ``doc_type`` means "9 법령, 59 고시" reads the way the source does.

    It is **derived, never stored**: a category is ``doc_type`` plus, for an annex, the *parent's*
    ``doc_type``. Storing it would be a third copy of a fact ``documents`` already holds twice.
    """

    STATUTE = "statute"  # 1. 현행법령 — 법률 · 시행령 · 시행규칙
    ADMIN_RULE = "admin_rule"  # 2. 현행 행정규칙 — 고시
    STATUTE_ANNEX = "statute_annex"  # 3. 법령 별표·서식
    ADMIN_RULE_ANNEX = "admin_rule_annex"  # 4. 행정규칙 별표·서식
    FEED = "feed"  # not part of the taxonomy — a change signal, not a holding
    OTHER = "other"


#: Display order. 법령 before 행정규칙 before their annexes — the authority's own ordering, and the
#: same priority the source map's blocks descend in.
DOC_CATEGORY_ORDER: Final[tuple[DocCategory, ...]] = (
    DocCategory.STATUTE,
    DocCategory.ADMIN_RULE,
    DocCategory.STATUTE_ANNEX,
    DocCategory.ADMIN_RULE_ANNEX,
    DocCategory.FEED,
    DocCategory.OTHER,
)

_STATUTE_TYPES: Final[frozenset[str]] = frozenset({"law", "decree", "enforcement_rule"})


def doc_category(doc_type: str, parent_doc_type: str | None = None) -> DocCategory:
    """Which taxonomy bucket a document falls in.

    ``parent_doc_type`` is required for an annex and ignored otherwise: 별표 of a 법령 and 별표 of a
    고시 are *different categories* to the authority, and the annex row itself cannot tell them
    apart — ``doc_type`` is ``annex`` for both.
    """
    if doc_type in _STATUTE_TYPES:
        return DocCategory.STATUTE
    if doc_type == "notice":
        return DocCategory.ADMIN_RULE
    if doc_type == "annex":
        return (
            DocCategory.ADMIN_RULE_ANNEX
            if parent_doc_type == "notice"
            else DocCategory.STATUTE_ANNEX
        )
    if doc_type == "feed":
        return DocCategory.FEED
    return DocCategory.OTHER


class VersionStatus(StrEnum):
    """Where a version sits relative to today (ADR-0016 decision 6).

    **Derived from ``effective_date`` alone — there is no status column.** A stored flag would
    duplicate the date and then disagree with it the morning a pending version comes into force,
    and nothing would run to flip it. The date already answers the question and keeps answering it
    as time passes.
    """

    IN_FORCE = "in_force"  # 시행중 — the latest version whose date has arrived
    PENDING = "pending"  # 시행예정 — 공포되었으나 아직 시행 전
    SUPERSEDED = "superseded"  # 지난 버전 — in force once, replaced by a later one
    UNKNOWN = "unknown"  # 부칙이 조건만 말해 날짜를 확정하지 못함 (ADR-0013)


def in_force_date(dates: Iterable[date | None], *, today: date) -> date | None:
    """The effective date of the version currently in force: the latest one that has arrived.

    Returns ``None`` where nothing has come into force yet — a real state for an instrument whose
    every version is still pending, and one that must not silently fall back to "the newest".
    """
    arrived = [value for value in dates if value is not None and value <= today]
    return max(arrived) if arrived else None


def version_status(
    effective_date: date | None, *, in_force: date | None, today: date
) -> VersionStatus:
    """Classify one version against its siblings' in-force date.

    The boundary is evaluated in the server's date, which is UTC. Korean effective dates are KST, so
    a version can read as pending for a few hours after it takes effect in Korea. Harmless for a
    browser label; it would matter for alert ordering, which is phase 1.4's problem to solve with a
    timezone the authority would recognise.
    """
    if effective_date is None:
        return VersionStatus.UNKNOWN
    if effective_date > today:
        return VersionStatus.PENDING
    return (
        VersionStatus.IN_FORCE
        if in_force is not None and effective_date == in_force
        else VersionStatus.SUPERSEDED
    )


class FetchOutcome(StrEnum):
    """Result of one fetch attempt. Recorded on **every** attempt (ADR-0003 decision 3)."""

    CHANGED = "changed"  # new content_hash → a DocumentVersion was created
    UNCHANGED = "unchanged"  # same content_hash → observation only, no version
    NOT_MODIFIED = "not_modified"  # HTTP 304 — the cheapest possible observation
    SKIPPED = "skipped"  # non-ingestible source; never fetched
    ERROR = "error"  # transport failure, or an authority error behind HTTP 200


class AttachmentKind(StrEnum):
    """A file link carried by a version. Annex *content* is a child Document, not an attachment."""

    ANNEX_FILE = "annex_file"  # 별표서식파일링크 — archival copy / fallback
    FORM = "form"  # 서식
    OTHER = "other"


class StandardStatus(StrEnum):
    """Tier D recognition status. Metadata only — there is nowhere to put the standard's text."""

    RECOGNIZED = "recognized"
    HARMONIZED = "harmonized"
    WITHDRAWN = "withdrawn"
    SUPERSEDED = "superseded"
    UNKNOWN = "unknown"


class ClauseKind(StrEnum):
    """What shape of content a ``Clause`` holds. **Domain-neutral** (ADR-0002 decision 3).

    The split is prose vs. table vs. form — a *content* distinction present in both domains — never
    SaMD vs. Cosmetic. 별표 3 of the cosmetic 고시 is pure prose and 의료기기 기준규격 is
    table-heavy, so a domain-keyed value here would be wrong in both directions.
    """

    PROSE = "prose"  # 조/항/호/목, and prose items inside an annex
    HEADING = "heading"  # 편/장/절/관, and section headings inside an annex
    TABLE = "table"  # a box-drawing table node; carries the column map (ADR-0014 dec 4)
    TABLE_ROW = "table_row"  # one logical row of a table
    FORM = "form"  # a whole 서식/별지 — a blank template has no rows worth addressing


class ChangeKind(StrEnum):
    """How a clause differs between two versions (ADR-0002 decision 7).

    ``RENUMBERED`` exists so that a renumbered-but-unchanged clause is never reported as
    ``REMOVED`` + ``ADDED``; MFDS 고시 renumber routinely and that pair would be two false alerts.
    """

    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"
    RENUMBERED = "renumbered"  # same content, its own number changed
    #: Same content and the **same clause number**, relocated under a different parent — 제8조 moved
    #: from 제2장 to 제3장. Never a mere shift in reading order: inserting one article changes every
    #: ordinal below it, and emitting those is how 37 real edits get buried under 1,209 empty ones.
    MOVED = "moved"


class DriftSignal(StrEnum):
    """Why the fetch or parse stage failed closed (ADR-0003 decision 6). Never a ChangeEvent."""

    ZERO_RECORDS = "zero_records"
    RECORD_COUNT_DELTA = "record_count_delta"
    MISSING_ROOT = "missing_root"
    AUTH_FAILURE = "auth_failure"  # the authority answered 200 with an error body
    EMPTY_ANNEX_BODY = "empty_annex_body"  # 별표내용 empty → file-link fallback needed
    ZERO_CLAUSES = "zero_clauses"  # parse stage: the body yielded nothing addressable
    CLAUSE_COUNT_DELTA = "clause_count_delta"  # parse stage: count moved beyond the threshold


#: Fraction by which a version's clause count may differ from the previous version of the same
#: document before the parse stage refuses it as drift (ADR-0003 decision 6).
#:
#: ADR-0003 open question 5 calls clause-count delta "a crude signal" needing calibration, and it is
#: right. 0.5 is deliberately loose: the largest genuine amendment observed in the gated corpus is
#: 화장품법 현행 (74 조문) → MST 282015 (79 조문), a 6.8% move, and the 시행예정 fetches add whole
#: articles at once. A threshold tight enough to catch a subtle mis-parse would reject real
#: amendments, and rejecting a real amendment is the worse error: it creates no version and emits no
#: change event, so a missed one is invisible to the detection-coverage gate.
CLAUSE_COUNT_DRIFT_RATIO: Final[float] = 0.5

#: Below this content-similarity ratio a renumber candidate is not accepted automatically.
#: Above it but below ``RENUMBER_CONFIDENT_RATIO`` the diff is written and flagged for RA review.
RENUMBER_MATCH_RATIO: Final[float] = 0.60
RENUMBER_CONFIDENT_RATIO: Final[float] = 0.90


#: Authoritative language per authority (ADR-0002 decision 5). Diffs are computed within one
#: language; other languages are retained for display only.
AUTHORITATIVE_LANGUAGE: Final[dict[Authority, str]] = {
    Authority.MFDS: "ko",
    Authority.FDA: "en",
    Authority.EU: "en",
    Authority.NMPA: "zh",
}

#: 소관부처 code for the 행정규칙 목록 API's ``org`` parameter (ADR-0003 decision 11).
#:
#: A **public identifier, not a credential** — it belongs in reviewed, version-controlled code
#: rather than in a gitignored ``.env`` file, where nobody could see it and every environment would
#: have to rediscover it. Verified live 2026-08-03: ``org=1471000`` returns 511 행정규칙, all with
#: ``소관부처명 = 식품의약품안전처``.
#:
#: MFDS only. The other three authorities have no equivalent parameter, and the discovery sweep is
#: MFDS-specific in Phase 1.
MFDS_ORG_CODE: Final[str] = "1471000"

#: Which cell an upstream 행정규칙 title plausibly belongs to. Deliberately over-inclusive: the
#: sweep produces a triage list for a human, and a 고시 missed because the filter was clever is a
#: coverage hole, while a 고시 wrongly listed costs one glance.
#:
#: **A regulation can govern a domain without naming it**, and title matching cannot see those.
#: ``색소`` and ``인체적용제품`` were added 2026-08-06, after ``scripts/admrul_triage.py`` measured
#: what the filter was missing:
#:
#: - ``색소`` → 의약품등의 타르색소 지정과 기준 및 시험방법, a cosmetic colorant standard that
#:   화장품의 색소 종류 및 기준 cross-references. Names neither 화장품 nor 의료기기.
#: - ``인체적용제품`` → 인체적용제품의 위해성평가에 관한 규정. The statutory category covers 화장품
#:   **and** 의료기기, so it maps to both cells.
#:
#: Each adds exactly **one** row against the live 511, measured before being added. Terms that were
#: tried and rejected on the same evidence: ``이물`` and ``부작용`` match only 식품/의약품 rules,
#: ``의약외품`` is not one of the 8 cells, and ``원료`` pulls in 건강기능식품 and 마약류.
#:
#: Widen this the same way — run the triage script, read its 🟡 bucket, and add a term only once
#: something in it is genuinely in scope. Guessing terms is how the list becomes unreadable, and an
#: unread triage list is the same coverage hole by a slower route.
DISCOVERY_KEYWORDS: Final[dict[str, tuple[str, ...]]] = {
    "mfds_samd": ("의료기기", "디지털의료제품", "인체적용제품"),
    "mfds_cosmetic": ("화장품", "색소", "인체적용제품"),
}

#: Titles the keywords catch but that are **out of scope by decision** (2026-08-06). Exclusion beats
#: inclusion in :func:`~app.discovery.cells_for`.
#:
#: A negative list is needed because the keywords are substrings: 체외진단의료기기 contains
#: 의료기기, so dropping a ``체외진단`` keyword would not have excluded anything.
#: `docs/import-source-map.md` records *why* — this constant is the enforcement, not the rationale.
#:
#: Each term is measured against the live 511 before being added; the counts are what a reviewer
#: should re-derive with ``scripts/admrul_triage.py`` rather than trust. Excluded rows stay
#: **visible** in that report under their own bucket: "seen and rejected" and "never seen" are
#: different states, and only the first can be revisited.
DISCOVERY_EXCLUSIONS: Final[dict[str, str]] = {
    # 8 고시. 체외진단의료기기법 is a separate statute, absent from the catalog's Primary Laws;
    # monitoring its 고시 without the act they implement would be incoherent. Revisit only
    # together with adding 체외진단의료기기법 itself.
    "체외진단": "체외진단의료기기법 is a separate statute, not in the catalog",
    # 2 고시. R&D funding-programme administration — how a grant scheme is run, not a duty on a
    # product. Named in phase1.0 § Risks as out of scope even inside the filter.
    "범부처": "R&D funding-programme administration, not a product requirement",
    # --- how a programme is run, not what a product must do (2026-08-06) --------------------
    #
    # One category, four 고시. Each governs the machinery of oversight — who inspects, who sits on
    # the committee, who may sit the exam, who may teach the course — and none states an obligation
    # a manufacturer could be found non-compliant against. They would be pure noise in an IR
    # extraction whose unit is "one bearer + one modal + one required action" (ADR-0004 decision 1).
    #
    # ``감시원`` covers **both** the device and cosmetic citizen-inspector rules. It was narrowed to
    # 소비자의료기기감시원 when only the device one had been decided; now that both are out, the
    # general term is correct and the asymmetry is gone.
    "감시원": "citizen-inspector programme administration, not a product requirement",
    "의료기기위원회": "advisory-committee constitution, not a product requirement",
    "자격시험": "qualification-exam administration, not a product requirement",
    "교육실시기관": "training-provider designation, not a product requirement",
}

#: Identify ourselves to government hosts (ADR-0003 decision 9). Contactable, not anonymous.
USER_AGENT: Final[str] = "RegOps-ImportAgent/0.1 (+https://github.com/hrkim1000/regops)"

#: Minimum gap between two requests to the same host, seconds. Politeness is part of the contract:
#: getting rate-limited off MFDS during the pilot would take out both gated cells at once.
HOST_MIN_INTERVAL_SECONDS: Final[float] = 1.0

#: Query-string parameters that must be redacted before a URL is logged (ADR-0003 decision 13).
#: The audit trail is append-only — a credential written into it cannot be cleaned up.
CREDENTIAL_PARAMS: Final[frozenset[str]] = frozenset({"OC", "oc", "key", "apikey", "api_key"})

#: Placeholder used inside ``sources.url_template``. The resolved URL is built at request time and
#: is never persisted, never logged, and never written to a fetch_observation.
CREDENTIAL_PLACEHOLDER: Final[str] = "{OC}"

#: Record fields that change on every poll without the content changing. Dropped before hashing
#: (ADR-0003 decision 2); ``조회수`` is the element confirmed volatile on MFDS listings.
VOLATILE_RECORD_FIELDS: Final[frozenset[str]] = frozenset(
    {"조회수", "조회 수", "hit", "hits", "viewcount", "view_count", "readcount"}
)


#: Token types. ``access`` is the only one Phase 0 issues.
TOKEN_TYPE_ACCESS: Final[str] = "access"
TOKEN_TYPE_REFRESH: Final[str] = "refresh"


class IRStatus(StrEnum):
    """IR lifecycle (ADR-0004 decision 4). Only ``LOCKED`` IRs flow downstream."""

    DRAFT = "draft"
    LOCKED = "locked"
    STALE = "stale"  # a cited clause was amended; re-extraction pending (ADR-0004 decision 5)
    SUPERSEDED = "superseded"


#: Stamped onto every ``document_versions.parser_version`` and used to decide whether a stored parse
#: is stale. Bump it whenever a profile changes what it emits — that is the signal to re-parse the
#: archive, which ADR-0015 makes possible without re-fetching.
PARSER_VERSION: Final[str] = "1.1.0"

#: Embeddings are pinned regardless of the generation provider (ADR-0005 decision 7).
EMBEDDING_MODEL: Final[str] = "nomic-embed-text"
EMBEDDING_DIM: Final[int] = 768

#: Genesis value for the first audit_log row's ``prev_hash`` (ADR-0011).
AUDIT_CHAIN_GENESIS: Final[str] = "0" * 64
