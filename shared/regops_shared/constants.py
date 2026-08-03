"""Shared constants. No magic literals in service code."""

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


class DriftSignal(StrEnum):
    """Why the parse stage failed closed (ADR-0003 decision 6). Never a ChangeEvent."""

    ZERO_RECORDS = "zero_records"
    RECORD_COUNT_DELTA = "record_count_delta"
    MISSING_ROOT = "missing_root"
    AUTH_FAILURE = "auth_failure"  # the authority answered 200 with an error body
    EMPTY_ANNEX_BODY = "empty_annex_body"  # 별표내용 empty → file-link fallback needed


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
DISCOVERY_KEYWORDS: Final[dict[str, tuple[str, ...]]] = {
    "mfds_samd": ("의료기기", "디지털의료제품", "체외진단"),
    "mfds_cosmetic": ("화장품",),
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

#: Embeddings are pinned regardless of the generation provider (ADR-0005 decision 7).
EMBEDDING_MODEL: Final[str] = "nomic-embed-text"
EMBEDDING_DIM: Final[int] = 768

#: Genesis value for the first audit_log row's ``prev_hash`` (ADR-0011).
AUDIT_CHAIN_GENESIS: Final[str] = "0" * 64
