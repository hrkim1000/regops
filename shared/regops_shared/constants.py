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
    #: A codified agency rule issued directly under a statute — a CFR Part (ADR-0018 decision 3).
    #: Deliberately *not* mapped onto ``ENFORCEMENT_RULE``: that name marks a rung of the Korean
    #: statutory ladder (법률 → 시행령 → 시행규칙), and a CFR Part has no 시행령 tier above it, so
    #: reusing it would assert a hierarchy that does not exist.
    REGULATION = "regulation"
    #: A statute as codified into a subject-arranged code — a USC chapter (ADR-0018 decision 12).
    #: Deliberately *not* mapped onto ``LAW``: that value names 법률 and routes to a profile that
    #: reads 조/항/호/목 as XML elements, while a USC granule is HTML that is not well-formed XML.
    #: The two are different envelopes, which is what ``doc_type`` selects on (ADR-0002 decision 3).
    CODIFIED_STATUTE = "codified_statute"


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


#: The only statuses downstream consumers may read (ADR-0004 decision 4). Retrieval, impact grading
#: and gap analysis filter on this — a draft IR is inert, and a stale one is an obligation whose
#: evidence has moved out from under it. Both would look like findings if they leaked.
IR_VISIBLE_STATUSES: Final[tuple[IRStatus, ...]] = (IRStatus.LOCKED,)


class ClassificationKind(StrEnum):
    """Every clause is examined and gets one of these (ADR-0004 decision 6).

    There is no third value and no absence. "50 IRs from 200 clauses" is uninterpretable unless the
    other 150 are on record as *examined and deliberately empty* — otherwise it cannot be told apart
    from 150 missed obligations, and gap-analysis completeness has nothing to rest on.
    """

    OBLIGATION_BEARING = "obligation_bearing"
    EXCLUDED = "excluded"


class ExclusionReason(StrEnum):
    """Why an examined clause yielded no IR. Required whenever ``kind = excluded``.

    A free-text reason would be unaggregatable, and the coverage claim depends on being able to say
    *how many* clauses were excluded for each reason — a sudden jump in ``UNPARSEABLE`` is a parser
    regression wearing an extraction costume.
    """

    DEFINITION = "definition"  # 정의 조항 — states what a term means, binds nobody
    SCOPE = "scope"  # 목적 / 적용범위
    HEADING = "heading"  # 편/장/절/관 and annex section headings
    PERMISSIVE = "permissive"  # 할 수 있다 / may — ADR-0004 decision 1, no IR
    PROCEDURAL = "procedural"  # 시행일, 경과조치 and other administrative machinery
    DELEGATION = "delegation"  # "…는 총리령으로 정한다" — defers the duty rather than stating one
    TABLE_CONTAINER = "table_container"  # a table node; its rows carry the obligations, not it
    FORM = "form"  # a blank 서식/별지 template
    EMPTY = "empty"  # no substantive text (a stub or a structural placeholder)
    NO_OBLIGATION = "no_obligation"  # examined, prose, and simply states no duty
    UNPARSEABLE = "unparseable"  # the agent returned nothing usable; recorded, never silently
    #: The *instrument* binds nobody — FDA guidance is explicitly nonbinding, so extraction skips it
    #: by ``doc_type`` and every clause is recorded excluded for this reason (ADR-0018 decision 9).
    #: Distinct from :attr:`PERMISSIVE`, which is about a modal inside a binding instrument.
    NON_BINDING = "non_binding"


class ExtractionRunStatus(StrEnum):
    """Where one extraction run got to. A run that dies mid-corpus must be visibly incomplete."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


#: Obligation modals per language, fixed at W3-4 (ADR-0004 decision 1). The inventory is *closed*:
#: an extracted IR whose modal is not in its language's tuple is rejected, because "one bearer + one
#: modal + one required action" is only a rule if the modal set is enumerable.
#:
#: Keyed by language rather than by domain — a modal is a property of Korean, not of cosmetics.
MODAL_INVENTORY: Final[dict[str, tuple[str, ...]]] = {
    "ko": ("하여야 한다", "해야 한다", "도록 한다", "금지한다", "아니 된다"),
    "en": ("shall", "must", "is required to", "may not"),
}

#: Permissive forms yield **no IR** (ADR-0004 decision 1). They are recorded as context on a related
#: IR where one exists, and as an ``ExclusionReason.PERMISSIVE`` classification where none does.
PERMISSIVE_MODALS: Final[dict[str, tuple[str, ...]]] = {
    "ko": ("할 수 있다", "수 있다"),
    "en": ("may", "can", "is permitted to"),
}

#: Obligation taxonomy per domain (ADR-0004 decision 3). This and the modal inventory and the prompt
#: are the **entire** content of the domain branch — same tables, same stages, same lifecycle.
#:
#: **The SaMD set grew on 2026-08-25, and the measurement is why.** The original four read as though
#: drawn from 21 CFR 820, and they were: triaged across the FDA corpus, Part 820 supplies **21 of
#: 341** obligation-bearing SaMD clauses — 6% — while ``design_control``/``risk``/``vnv`` describe
#: nothing outside it. The rest had no home at all:
#:
#: =========================================  =====  ==================================
#: Part                                       Obl.   Code
#: =========================================  =====  ==================================
#: 803 medical device reporting                  82  ``postmarket``
#: 892 radiology device classification           68  ``classification``  *(new)*
#: 807 establishment registration & listing      63  ``registration``    *(new)*
#: 860 device classification procedures          34  ``classification``  *(new)*
#: 822 postmarket surveillance                   23  ``postmarket``
#: 7   enforcement policy & recalls              21  ``postmarket``
#: 820 quality management system                 21  ``design_control`` · ``risk`` · ``vnv``
#: 11  electronic records & signatures           18  ``records``         *(new)*
#: 806 corrections & removals                    11  ``postmarket``
#: =========================================  =====  ==================================
#:
#: ``postmarket`` **deliberately absorbs** MDR, surveillance, corrections/removals and recalls: all
#: four are duties that attach after a device is on the market, and splitting them would multiply
#: codes without separating obligations an RA treats differently.
#:
#: It does **not** absorb registration, classification or records, and that was the alternative
#: considered and rejected: 892/807/860/11 are pre-market and market-entry duties, so filing them
#: under ``postmarket`` would make the code's name false — worse than having no code, because a
#: wrong label reads as information.
#:
#: **Cosmetic is unchanged, and now assessed rather than merely unmeasured** (2026-08-25, after the
#: three Parts that had failed to fetch were re-collected). All four cosmetic Parts are ingested and
#: the five existing codes cover every obligation in them:
#:
#: ======================================  =====  ==============
#: Part                                    Obl.   Code
#: ======================================  =====  ==============
#: 701 cosmetic labeling                      63  ``labelling``
#: 700 general — CFC propellants, prohibited
#: cattle materials, sunscreen ingredients    16  ``ingredient``
#: 740 warning statements                     12  ``labelling``
#: 710 voluntary establishment registration    0  —
#: ======================================  =====  ==============
#:
#: Part 710 yields **no obligations at all**, which is consistent rather than surprising: it is the
#: *voluntary* registration Part, and it likewise has zero Federal Register final rules.
#:
#: ``claims``, ``gmp`` and ``notification`` are unexercised by this corpus and are **kept**. They
#: exist for the MFDS cell, and MoCRA's facility-registration and product-listing duties live in the
#: FD&C Act and Cosmetics Direct rather than in these Parts — so ``notification`` is waiting for a
#: source that is not ingested yet, not for want of a code.
TAXONOMY_CODES: Final[dict[Domain, tuple[str, ...]]] = {
    Domain.SAMD: (
        "design_control",
        "risk",
        "vnv",
        "postmarket",
        "registration",
        "classification",
        "records",
    ),
    Domain.COSMETIC: ("ingredient", "labelling", "claims", "gmp", "notification"),
}

#: Bumped when the atomicity rules, modal inventory or taxonomy change. Stamped on every IR: an
#: obligation extracted under an older rule set is not comparable with one extracted under this one,
#: and the golden-set score is only meaningful per rule version.
#:
#: **1.3.0 (2026-08-25) — three SaMD taxonomy codes added.** The modal inventory and the atomicity
#: rules are untouched, so *whether* a clause bears an obligation is unchanged; only the label it
#: can carry moved. The bump is still required, and the cost is real: every IR already stored is
#: stamped ``1.2.0``, the gated MFDS ones included, and phase1.6's golden-set scores were measured
#: against that version. They stay valid *for it* and are not comparable with anything extracted
#: from here on. Re-extracting the MFDS corpus under 1.3.0 would restore comparability and cost a
#: agent pass over 25,729 clauses — a decision for whoever next needs the two sides compared, not a
#: side effect to slip into this change.
IR_RULE_VERSION: Final[str] = "1.3.0"

#: Bumped independently of the rules — a prompt can be reworded without the rule set moving.
IR_PROMPT_VERSION: Final[str] = "1.2.0"

#: Extraction is run at temperature 0 and any delta between two runs at the same
#: ``(rule_version, prompt_version, llm_model)`` is treated as a regression (ADR-0017 decision 1).
#: Sampling makes this approximate rather than guaranteed, which is why it is a *test*, not a claim.
EXTRACTION_TEMPERATURE: Final[float] = 0.0

#: Clauses per LLM call. One at a time: the atomicity rule is about a single clause's obligations,
#: and batching invites the model to merge duties across clause boundaries — the exact error that
#: makes IR counts non-comparable.
EXTRACTION_BATCH_SIZE: Final[int] = 1

#: How many clauses are written before the orchestrator commits. Long work commits incrementally so
#: progress survives a worker restart and a retry skips what is already classified.
EXTRACTION_COMMIT_EVERY: Final[int] = 25


#: Stamped onto every ``document_versions.parser_version`` and used to decide whether a stored parse
#: is stale. Bump it whenever a profile changes what it emits — that is the signal to re-parse the
#: archive, which ADR-0015 makes possible without re-fetching.
PARSER_VERSION: Final[str] = "1.1.0"

#: Embeddings are pinned regardless of the generation provider (ADR-0005 decision 7).
EMBEDDING_MODEL: Final[str] = "nomic-embed-text"
EMBEDDING_DIM: Final[int] = 768


class EmbeddingScope(StrEnum):
    """What a stored vector actually covers (ADR-0006 decisions 1–2).

    The unit is the **조**, not the clause: a 호 embedded alone is unretrievable — ``3. 갈색``
    carries no meaning without its parent. So one vector covers an article with its 항/호/목 rolled
    in, and citation still resolves to whichever child the answer used.

    ``TABLE_HEADER`` is the annex compromise. Rows are never embedded — thousands of near-identical
    ingredient lines are the worst possible input to a semantic index — but the table's title and
    column labels are, so *"화장품에 쓸 수 없는 원료 목록이 있나?"* still finds the annex and the
    lookup that follows is relational.
    """

    ARTICLE = "article"  # a 조 (or § / regulation-level unit) with its children rolled in
    ARTICLE_FRAGMENT = "article_fragment"  # a long 조, split at 항 boundaries, heading re-prepended
    TABLE_HEADER = "table_header"  # an annex table's title + column labels — never its rows
    FORM = "form"  # a blank 서식/별지: its title is all there is to retrieve on


#: Characters per embedded passage before it is split (ADR-0006 decision 1).
#:
#: ``nomic-embed-text`` takes 2,048 tokens, and the conversion from characters is *worse* for Korean
#: than for English rather than better: a hangul syllable is three UTF-8 bytes and BPE typically
#: spends more than one token on it, so 2,000 characters of 고시 text overruns the window. Measured
#: on the gated corpus, an unbounded pass produced passages of 21,588 characters — a whole 서식 with
#: an embedded table — and Ollama answered those with **HTTP 500** rather than truncating, which is
#: why this is a hard cap enforced on every passage and not only on long articles.
#:
#: 1,200 leaves margin for the heading each fragment re-prepends. Changing it changes every stored
#: vector, so bump :data:`EMBEDDING_PASSAGE_VERSION` with it.
MAX_PASSAGE_CHARS: Final[int] = 1200

#: Passages embedded before the pipeline commits. Same reasoning as ``EXTRACTION_COMMIT_EVERY``:
#: long work commits incrementally so a worker restart resumes instead of restarting.
EMBEDDING_COMMIT_EVERY: Final[int] = 50

#: Bumped when passage construction changes — a vector built under an older assembly rule is not
#: comparable with one built under this one, and the stored value is what decides re-embedding.
EMBEDDING_PASSAGE_VERSION: Final[str] = "1.3.1"


# --- retrieval (ADR-0006 decision 3) -------------------------------------------------------

#: Candidates each retrieval arm contributes before fusion, and how many survive it.
RETRIEVAL_CANDIDATES: Final[int] = 40
RETRIEVAL_TOP_K: Final[int] = 8

#: Reciprocal-rank-fusion damping. The standard 60 — large enough that the top few ranks of the two
#: arms are close in weight, so a result found by both beats one found deeply by either.
RRF_K: Final[int] = 60

#: Arm weights for fusion. Lexical is weighted **above** vector, which is not the usual default:
#: regulatory corpora are identifier-dense (ADR-0006 decision 3), and 원료명 / CAS 번호 / 조문 번호
#: are the questions RA staff ask most. ADR-0006 open question 2 leaves the exact ratio to be tuned
#: against the golden set — these are a starting point, not a measured optimum.
RETRIEVAL_LEXICAL_WEIGHT: Final[float] = 1.2
RETRIEVAL_VECTOR_WEIGHT: Final[float] = 1.0

#: An identifier the query names outright (제5조, 별표 1, § 892.2050) resolves **exactly** and is
#: placed above every fused result. ``65-29-2`` has no useful embedding; an exact match on it does.
RETRIEVAL_IDENTIFIER_BOOST: Final[float] = 100.0

#: Postgres text-search configuration for the lexical arm. ``simple`` deliberately: the stemming
#: configurations are language-specific and there is none for Korean, so anything else would stem
#: English tokens inside a Korean corpus and leave the rest untouched.
FTS_CONFIG: Final[str] = "simple"

#: Per-language override. ``simple`` stays the default and the Korean answer; English gets the
#: stemmer, because without it ``requirement`` and ``requirements`` are unrelated tokens and the
#: lexical arm loses most of its recall on the vocabulary a regulatory corpus is built from —
#: measured at +679% on ``requirement`` over the FDA corpus (migration 0010).
#:
#: A language absent from this map falls back to :data:`FTS_CONFIG`, which is the safe direction: an
#: unknown language gets no stemming rather than the wrong stemming.
FTS_CONFIG_BY_LANGUAGE: Final[dict[str, str]] = {"en": "english"}


def fts_config_for(language: str | None) -> str:
    """The Postgres text-search configuration for a version's language."""
    return FTS_CONFIG_BY_LANGUAGE.get((language or "").lower(), FTS_CONFIG)


# --- generation and verification (ADR-0006 decisions 4–8) ----------------------------------


class AnswerStatus(StrEnum):
    """Where an answer ended up. Two of these are *successes*.

    ``NEEDS_VERIFICATION`` is the promise in RegOps.md kept, not a failure — no unsourced answer is
    ever emitted. ``NEEDS_REVIEW`` is the sub-threshold-confidence route: the answer has citations
    and survived verification, but not by enough to reach a user as final.
    """

    ANSWERED = "answered"
    NEEDS_VERIFICATION = "needs_verification"
    NEEDS_REVIEW = "needs_review"


#: The only status a caller may present as a final answer. Everything else is on its way to a human.
ANSWER_FINAL_STATUSES: Final[tuple[AnswerStatus, ...]] = (AnswerStatus.ANSWERED,)


class VerificationVerdict(StrEnum):
    """One claim, judged against the clause text it cites — and nothing else (decision 6).

    A verifier that can only annotate is theatre, so ``UNSUPPORTED`` fails the answer outright.
    ``PARTIAL`` does not fail it but costs confidence, which is what routes borderline answers to
    review instead of silently downgrading them with a caveat.
    """

    SUPPORTED = "supported"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"


#: Why an answer could not be given. Recorded rather than left to prose: the "needs verification"
#: rate is a monitored two-sided metric (ADR-0006 decision 7), and a rate is uninterpretable if the
#: reasons behind it cannot be counted.
class NoAnswerReason(StrEnum):
    NO_RETRIEVAL = "no_retrieval"  # nothing in the cell matched at all
    NO_CITATION = "no_citation"  # the model answered without citing anything
    FABRICATED_CITATION = "fabricated_citation"  # cited a clause retrieval never returned (dec 4)
    UNSUPPORTED_CLAIM = "unsupported_claim"  # the verification pass rejected a claim (dec 6)
    UNPARSEABLE = "unparseable"  # the model returned nothing usable
    #: The model could not be reached, or did not answer in time. Recorded rather than raised: a
    #: question that was asked must end in a stored outcome, or the rate in decision 7 silently
    #: excludes every failure and the asker watches a spinner forever.
    MODEL_UNAVAILABLE = "model_unavailable"


#: Below this, an answer routes to human review rather than reaching the user as final.
#:
#: 0.7 is not a round number picked for looking careful — it is where the weights below put the
#: boundary between two specific outcomes:
#:
#: - every claim only ``partial``, cited at rank 1 → ``0.7·0.5 + 0.3·1.0 = 0.65`` → **review**
#: - every claim ``supported``, cited at the *worst* surviving rank → ``0.7·1.0 + 0.3·0.125 =
#:   0.7375`` → **final**
#:
#: So an answer whose evidence only half-establishes it always reaches a human, and one that is
#: fully supported is not sent to review merely for having been found deep in the ranking. Move
#: either weight and this number has to be re-derived, not nudged. Phase 1.6 re-calibrates it
#: against the golden set — a threshold nobody measures is a guess with a decimal point.
ANSWER_CONFIDENCE_THRESHOLD: Final[float] = 0.7

#: Confidence weights. Verification dominates on purpose: mis-citation is the hallucination class
#: that survives every structural check (ADR-0006 decision 5), so how the verifier voted has to
#: outweigh how well retrieval scored.
CONFIDENCE_VERIFICATION_WEIGHT: Final[float] = 0.7
CONFIDENCE_RETRIEVAL_WEIGHT: Final[float] = 0.3

#: Generation runs at temperature 0 for the same reason extraction does (ADR-0017 decision 1):
#: a delta between two runs at the same (prompt_version, model) is a regression to investigate.
GENERATION_TEMPERATURE: Final[float] = 0.0

#: Bumped when the answer or verification prompt changes. A citation-accuracy score is only
#: comparable within one prompt version.
#: 1.3.1 dropped the free-text ``answer`` field: the answer is composed from the validated claims,
#: so every sentence a reader sees carries a citation and faces verification. It also roughly halves
#: output tokens, which on a small local model is the difference between a usable answer and a
#: timeout — measured at ~3 tokens/second.
ANSWER_PROMPT_VERSION: Final[str] = "1.3.1"
VERIFICATION_PROMPT_VERSION: Final[str] = "1.3.0"

#: Bumped when passage assembly, fusion or scoping changes what retrieval returns. Stored on the
#: answer, because "which clauses were even available to cite" is part of an answer's provenance.
#: 1.4.0 (2026-08-25): US identifiers normalised to the stored segment form and compound addresses
#: resolved as a path tail, plus a per-language text-search configuration. Both change what the
#: identifier and lexical arms return for an English scope; neither changes the Korean one.
RETRIEVAL_VERSION: Final[str] = "1.4.0"

#: Guard against a model that never stops. Real regulatory answers are a handful of claims; a reply
#: with more than this is a runaway, not a thorough analysis.
MAX_CLAIMS_PER_ANSWER: Final[int] = 12

#: Characters of clause text per passage in the generation prompt.
#:
#: **This is not the same bound as :data:`MAX_PASSAGE_CHARS` and forgetting that cost a working
#: query.** That one caps what gets *embedded*; a retrieval hit carries the raw clause text, which
#: has no bound at all. Measured on a live question in `mfds_samd`: eight hits totalling 185,161
#: characters, one 별표 clause contributing 130,603 of them — ≈58,000 tokens into a 32,768 window,
#: which Ollama truncates silently. The visible symptom was a three-minute timeout; the invisible
#: one is a model citing passages whose text was cut away before it ever saw them.
#:
#: Set to the same value as ``MAX_PASSAGE_CHARS`` on purpose: what the model reads should be the
#: unit retrieval actually matched, not an arbitrary window over something larger.
MAX_PROMPT_BLOCK_CHARS: Final[int] = MAX_PASSAGE_CHARS

#: Child paths listed as citable under one passage. A 조 with hundreds of 호 would otherwise spend
#: more of the prompt on its address list than on its text.
MAX_CITABLE_PATHS_PER_PASSAGE: Final[int] = 24

# --- monitoring: matching, grading, delivery (ADR-0009 decisions 2-3) ----------------------


class AlertChannel(StrEnum):
    """Where an alert is delivered.

    ``EMAIL`` is declared and **not implemented in Phase 1**: there is no mail relay in the stack,
    and a channel that silently drops would make the delivery-failure criterion untestable. It is
    named here so adding a relay is a channel implementation rather than an enum migration.
    """

    IN_APP = "in_app"  # recorded and read back from the API — the default
    WEBHOOK = "webhook"  # POST to a subscriber-configured URL
    EMAIL = "email"  # declared, unimplemented until a relay exists


class AlertSeverity(StrEnum):
    """Impact grade. **Cell-level, never product-level** (ADR-0007, ADR-0009 decision 5).

    Until the Product context exists an IR applies to a *cell*, so the strongest thing Phase 1 can
    say is "something in your cell changed, and here is how much of it". Presenting these as
    product-level precision would be a claim the data cannot support.
    """

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


#: Ordered least- to most-urgent, so ``min_severity`` on a subscription is an index comparison.
SEVERITY_ORDER: Final[tuple[AlertSeverity, ...]] = (
    AlertSeverity.LOW,
    AlertSeverity.MEDIUM,
    AlertSeverity.HIGH,
)


class AlertStatus(StrEnum):
    """Where an alert got to, derived from its deliveries after every pass.

    Three values, not four: a partial success reads as ``DELIVERED`` because the per-subscriber
    truth is on ``alert_deliveries``, and an alert-level "partial" would be a second copy of a fact
    that is already recorded per attempt.
    """

    PENDING = "pending"  # at least one delivery still has attempts left
    DELIVERED = "delivered"  # nothing retriable remains and at least one attempt succeeded
    FAILED = "failed"  # every subscriber's attempts are exhausted


class DeliveryStatus(StrEnum):
    """One attempt. The row is written *before* the attempt, so a crash mid-send leaves a record."""

    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


#: Change kinds that move a clause's **address** without changing what it requires
#: (:class:`ChangeKind`, ADR-0002 decision 7). An amendment consisting only of these produces no
#: end-user alert: it is not a substantive change, and false positives attack the detection-coverage
#: story from the side no gate measures.
NON_SUBSTANTIVE_CHANGE_KINDS: Final[frozenset[ChangeKind]] = frozenset(
    {ChangeKind.RENUMBERED, ChangeKind.MOVED}
)

#: Substantive clauses in one amendment above which it is graded ``MEDIUM`` on size alone.
#:
#: Deliberately crude, and labelled as such. Phase 1 grading has three inputs — change kind, clause
#: count, and whether a locked IR cites the touched text — and no corpus of graded amendments to
#: calibrate against. 20 sits above the largest routine 고시 touch-up and below a restructuring;
#: phase 1.6 re-derives it from the pilot rather than nudging it here.
ALERT_BULK_CLAUSE_COUNT: Final[int] = 20

#: Attempts per (alert, subscriber) before delivery is abandoned. Each attempt writes its own
#: ``alert_deliveries`` row, so an exhausted delivery is visible rather than merely absent.
DELIVERY_MAX_ATTEMPTS: Final[int] = 5

#: Exponential backoff, doubling from one minute and capped at six hours. Capped because the gate
#: is publication → alert within 24h: a backoff that grows without bound would let a relay that
#: recovers on day two report a success that missed the only deadline that matters.
DELIVERY_BACKOFF_BASE_SECONDS: Final[int] = 60
DELIVERY_BACKOFF_CAP_SECONDS: Final[int] = 6 * 60 * 60


def delivery_backoff_seconds(attempt: int) -> int:
    """Seconds to wait before ``attempt`` + 1. ``attempt`` is 1-based."""
    wait = DELIVERY_BACKOFF_BASE_SECONDS * 2 ** max(attempt - 1, 0)
    return min(wait, DELIVERY_BACKOFF_CAP_SECONDS)


#: The Go/No-Go detection-latency gate, measured publication → alert (RegOps.md).
DETECTION_LATENCY_TARGET_HOURS: Final[int] = 24

#: Window the daily briefing covers, ending at "now" in the authority's own timezone.
BRIEFING_WINDOW_HOURS: Final[int] = 24

#: The timezone an authority publishes in — what "today" means to the person being alerted.
#:
#: Not decoration, and the one thing :func:`version_status` explicitly defers to this phase: a
#: Korean effective date evaluated in UTC reads as pending for nine hours after it takes effect in
#: Korea. Harmless on a browser label, wrong on a *daily* briefing, whose whole content is decided
#: by where the day boundary falls.
AUTHORITY_TIMEZONE: Final[dict[Authority, str]] = {
    Authority.MFDS: "Asia/Seoul",
    Authority.FDA: "America/New_York",
    Authority.EU: "Europe/Brussels",
    Authority.NMPA: "Asia/Shanghai",
}


#: Genesis value for the first audit_log row's ``prev_hash`` (ADR-0011).
AUDIT_CHAIN_GENESIS: Final[str] = "0" * 64


# --- Evaluation: the Go/No-Go gates (phase 1.6) ------------------------------------------------
#
# The thresholds live here rather than in the harness because the harness is not the only reader:
# a service that reports one of these numbers must report it against the same line the gate is
# scored on, and two copies of "0.95" drift the moment one of them is tuned.


class EvaluationAxis(StrEnum):
    """The query shapes a golden set must cover, closed (ADR-0006 open question 4).

    The inventory is closed for one reason: a set of only identifier lookups measures the easy half
    and scores well doing it. Coverage is asserted **per axis per domain**, so a passing citation
    accuracy cannot rest on a handful of items in the hard categories.
    """

    #: 제5조, § 892.2050 — must resolve exactly, not fuzzily.
    IDENTIFIER = "identifier"
    #: The obligation asked in the reader's own words, with none of the statute's vocabulary.
    CONCEPTUAL = "conceptual"
    #: The answer differs depending on which version is in force (ADR-0006 decision 8).
    EFFECTIVE_DATE = "effective_date"
    #: The question asserts a clause that does not exist, or attributes content to the wrong one.
    MIS_CITATION = "mis_citation"
    #: Asked in the wrong cell. Declining is correct; answering from the neighbour is not
    #: (ADR-0006 decision 9).
    CROSS_DOMAIN = "cross_domain"
    #: No clause in the corpus answers it. "Needs verification" is the correct outcome, and is
    #: scored as one.
    UNANSWERABLE = "unanswerable"


class ExpectedOutcome(StrEnum):
    """What a golden item asserts the system should do. Two values, because there are two."""

    #: An answer with citations is correct here.
    ANSWERED = "answered"
    #: Refusing is correct here — the item is unanswerable, cross-domain, or a mis-citation trap.
    NEEDS_VERIFICATION = "needs_verification"


#: Per axis per domain. 200 items over six axes averages 33, and the phase file says plainly that
#: this is thin; the floor makes the thinness visible per axis instead of hiding it in an average.
GOLDEN_SET_MIN_ITEMS_PER_AXIS: Final[int] = 15

#: Share of actual amendments captured. Scored against **scheduled** polls, never observed ones —
#: a day the poller did not run leaves no ``fetch_observations`` row at all, so an observed-poll
#: denominator makes downtime *improve* the number.
DETECTION_COVERAGE_FLOOR: Final[float] = 0.95

#: Share of cited clauses that actually support the claim, by blind RA assessment. The mechanical
#: half (does the cited clause exist at that version) is a necessary condition, not this number.
CITATION_ACCURACY_FLOOR: Final[float] = 0.90

#: Outputs citing a clause that does not exist, or contradicting the source text. A ceiling, so the
#: comparison is ``<=``.
HALLUCINATION_RATE_CEILING: Final[float] = 0.02

#: Versus the manual process for the same query type. Unfalsifiable without a baseline captured
#: before the pilot starts.
RESEARCH_TIME_SAVING_FLOOR: Final[float] = 0.30

#: Voluntary use at least once a week for four consecutive weeks. The window cannot be compressed.
PILOT_RETENTION_FLOOR: Final[float] = 0.60
PILOT_RETENTION_WEEKS: Final[int] = 4

#: No-Go is called at this many shortfalls. A cell that misses is not offset by the other passing.
NO_GO_GATE_FAILURES: Final[int] = 4

#: Below this, two raters applying the atomicity rule do not land in the same place, and every
#: downstream count is non-comparable. Krippendorff's convention for content analysis.
IR_AGREEMENT_FLOOR: Final[float] = 0.80
