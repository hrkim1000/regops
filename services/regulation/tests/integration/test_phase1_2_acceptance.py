"""Phase 1.2 acceptance criteria, against the real stack.

    docker compose --profile app up -d
    docker compose run --rm migrate
    STAGE=test REGOPS_DB_NAME=regops_test docker compose run --rm regulation \
        python -m pytest tests/integration -q

Real Postgres and real MinIO. **The LLM is stubbed**, and that is not a shortcut: every criterion
here is about what the pipeline does with a model's answer — reject it, classify around it, or
freeze it on amendment — none of which is a claim about how well a given model reads Korean. Model
quality is measured against the golden set in phase 1.6, per domain, where it belongs.

Each test names the criterion it covers from
[phase1.2](../../../../docs/plan/phase1.2_ir_extraction.md) § Acceptance criteria.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from app.diff import diff_version
from app.extraction import domains_for, extract_version, rederive_version
from app.models import (
    IR,
    Cell,
    ChangeEvent,
    Clause,
    ClauseClassification,
    ClauseDiff,
    Document,
    DocumentCell,
    DocumentVersion,
    ExtractionRun,
    IRCitation,
    Source,
    StructureDriftAlert,
)
from app.parse import parse_version
from regops_shared.constants import (
    EXTRACTION_HEARTBEAT_STALE_AFTER,
    ClassificationKind,
    DocType,
    Domain,
    ExtractionRunStatus,
    IRStatus,
    SourceBlock,
    SourceTier,
)
from regops_shared.db import sync_session
from regops_shared.llm import Completion, LLMClient
from regops_shared.storage import archive_bytes

pytestmark = pytest.mark.integration

KEY_PREFIX = "test:phase12"
SLUG = "test.phase12.source"


# --- the stub model ---------------------------------------------------------------------------


class StubLLM(LLMClient):
    """A model that answers from a script keyed on the clause path in the prompt.

    Deliberately *not* a mock that returns one canned reply: several criteria turn on what happens
    when the model answers differently for different clauses — one obligation here, three there,
    a bogus citation somewhere else — and a single reply cannot exercise that.
    """

    provider = "stub"

    def __init__(self, replies: dict[str, list[dict]] | None = None, default: list | None = None):
        self.model = "stub-model"
        self._replies = replies or {}
        self._default = default if default is not None else []
        self.calls: list[str] = []
        self.temperatures: list[float | None] = []

    async def complete(self, prompt, *, system=None, temperature=None) -> Completion:
        self.temperatures.append(temperature)
        path = next(
            (key for key in sorted(self._replies, key=len, reverse=True) if f'"{key}"' in prompt),
            None,
        )
        self.calls.append(path or "?")
        payload = self._replies.get(path, self._default) if path else self._default
        text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
        return Completion(text=text, provider=self.provider, model=self.model)

    async def embed(self, text: str) -> list[float]:  # pragma: no cover - not used here
        raise NotImplementedError


def _ir_json(statement: str, *, cites: list[str], modal: str = "하여야 한다", **extra) -> dict:
    return {
        "bearer": "제조업자",
        "modal": modal,
        "statement": statement,
        "condition_text": None,
        "taxonomy_code": None,
        "cites": cites,
    } | extra


# --- fixtures ---------------------------------------------------------------------------------


def _purge(session) -> None:
    documents = list(
        session.scalars(select(Document).where(Document.canonical_key.startswith(KEY_PREFIX)))
    )
    ids = [d.id for d in documents]
    if ids:
        versions = list(
            session.scalars(select(DocumentVersion.id).where(DocumentVersion.document_id.in_(ids)))
        )
        if versions:
            runs = select(ExtractionRun.id).where(ExtractionRun.document_version_id.in_(versions))
            ir_ids = list(
                session.scalars(
                    select(IRCitation.ir_id).where(IRCitation.document_version_id.in_(versions))
                )
            )
            if ir_ids:
                # Break the supersession chain first, or the self-FK blocks the sweep. Then delete
                # the IRs and let `ir_citations` CASCADE — deleting citations by hand first would
                # leave the IR briefly uncited, and migration 0004's deferred trigger is right to
                # object to that in production even though this is only teardown.
                session.query(IR).filter(IR.id.in_(ir_ids)).update(
                    {IR.supersedes_ir_id: None}, synchronize_session=False
                )
                session.execute(delete(IR).where(IR.id.in_(ir_ids)))
            session.execute(delete(IRCitation).where(IRCitation.document_version_id.in_(versions)))
            clauses = select(Clause.id).where(Clause.document_version_id.in_(versions))
            session.execute(
                delete(ClauseClassification).where(ClauseClassification.clause_id.in_(clauses))
            )
            session.execute(delete(ExtractionRun).where(ExtractionRun.id.in_(runs)))
            diffs = select(ClauseDiff.id).where(ClauseDiff.to_version_id.in_(versions))
            session.execute(delete(ChangeEvent).where(ChangeEvent.clause_diff_id.in_(diffs)))
            session.execute(delete(ClauseDiff).where(ClauseDiff.to_version_id.in_(versions)))
            session.execute(delete(ClauseDiff).where(ClauseDiff.from_version_id.in_(versions)))
            session.execute(delete(Clause).where(Clause.document_version_id.in_(versions)))
        session.execute(delete(DocumentCell).where(DocumentCell.document_id.in_(ids)))
        session.execute(delete(DocumentVersion).where(DocumentVersion.document_id.in_(ids)))
        session.execute(delete(Document).where(Document.id.in_(ids)))

    for source in session.scalars(select(Source).where(Source.slug == SLUG)):
        session.execute(
            delete(StructureDriftAlert).where(StructureDriftAlert.source_id == source.id)
        )
        session.execute(delete(Source).where(Source.id == source.id))
    session.commit()


@pytest.fixture
def session():
    with sync_session() as db:
        _purge(db)
        yield db
        _purge(db)


@pytest.fixture
def cells(session) -> dict[str, uuid.UUID]:
    rows = session.scalars(select(Cell).where(Cell.slug.in_(["mfds_cosmetic", "mfds_samd"]))).all()
    assert len(rows) == 2, "migration 0001 seeds the 8 cells"
    return {cell.slug: cell.id for cell in rows}


@pytest.fixture
def source(session, cells) -> Source:
    row = Source(
        slug=SLUG,
        cell_id=cells["mfds_samd"],
        block=SourceBlock.PRIMARY_LAWS,
        ordinal=1,
        title="phase 1.2 fixture",
        tier=SourceTier.A,
        ingestible=True,
        connector="law_go_kr_law",
        url_template="https://example.invalid/{OC}",
        params={},
    )
    session.add(row)
    session.commit()
    return row


# --- builders ---------------------------------------------------------------------------------

#: 제5조 bears two obligations, 제2조 is a definition, 제6조 delegates, 제7조 is permissive. That
#: spread is the point: the coverage criterion is only meaningful over clauses that exercise more
#: than one exclusion reason.
ARTICLES = {
    "2": '정의) 이 법에서 사용하는 용어의 뜻은 다음과 같다. 1. "기록"이란 자료를 말한다.',
    "5": "기록의 보관) 제조업자는 기록을 3년간 보관하여야 하며, 매년 결과를 보고하여야 한다.",
    "6": "위임) 신고의 절차에 관하여 필요한 사항은 총리령으로 정한다.",
    "7": "자료제출) 식품의약품안전처장은 자료의 제출을 요구할 수 있다.",
}


def _law_xml(articles: dict[str, str], *, effective: str = "20260402") -> bytes:
    body = "".join(
        f'<조문단위 조문키="000{number}001">'
        f"<조문번호>{number}</조문번호><조문여부>조문</조문여부>"
        f"<조문시행일자>{effective}</조문시행일자>"
        f"<조문내용>제{number}조({text}</조문내용>"
        f"</조문단위>"
        for number, text in articles.items()
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<법령>
  <기본정보><법령ID>002015</법령ID><법종구분>법률</법종구분>
    <법령명_한글>테스트법</법령명_한글><공포일자>20250401</공포일자>
    <시행일자>{effective}</시행일자></기본정보>
  <조문>{body}</조문>
  <부칙><부칙단위><부칙공포일자>20250401</부칙공포일자>
    <부칙내용>제1조(시행일) 이 법은 공포한 날부터 시행한다.</부칙내용>
  </부칙단위></부칙>
</법령>
""".encode()


def _make_version(
    session,
    source: Source,
    *,
    raw: bytes,
    canonical_key: str,
    retrieved_at: datetime | None = None,
    claim: list[uuid.UUID] | None = None,
) -> DocumentVersion:
    document = session.scalar(select(Document).where(Document.canonical_key == canonical_key))
    if document is None:
        document = Document(
            canonical_key=canonical_key,
            title=canonical_key,
            doc_type=DocType.LAW,
            source_id=source.id,
        )
        session.add(document)
        session.flush()
    for cell_id in claim or [source.cell_id]:
        if session.get(DocumentCell, (document.id, cell_id)) is None:
            session.add(DocumentCell(document_id=document.id, cell_id=cell_id))

    object_key, digest = archive_bytes(raw, content_type="application/xml")
    version = DocumentVersion(
        document_id=document.id,
        version_group_id=uuid.uuid4(),
        language="ko",
        content_hash=digest,
        raw_object_key=object_key,
        raw_bytes=len(raw),
        content_type="application/xml",
        retrieved_at=retrieved_at or datetime.now(UTC),
    )
    session.add(version)
    session.commit()
    parse_version(session, version)
    return version


def _clause_path(session, version: DocumentVersion, number: str) -> str:
    clause = session.scalar(
        select(Clause).where(
            Clause.document_version_id == version.id,
            Clause.clause_path.like(f"%제{number}조"),
        )
    )
    assert clause is not None, f"제{number}조 not parsed"
    return clause.clause_path


# --- criterion: an uncited extraction is rejected ---------------------------------------------


def test_an_uncited_extraction_is_rejected_and_counted(session, source):
    """*An uncited extraction is rejected; no null-citation row can be written.*

    ADR-0004 decision 2. The model proposes an obligation whose ``cites`` name a clause that does
    not exist in this version, so nothing can be attached — and the proposal is dropped rather than
    stored against a null citation, where it would launder an unsourced claim into gap analysis.
    """
    version = _make_version(
        session, source, raw=_law_xml(ARTICLES), canonical_key=f"{KEY_PREFIX}:uncited"
    )
    path = _clause_path(session, version, "5")

    client = StubLLM({path: [_ir_json("보관", cites=["제99조/제9항"])]})
    result = extract_version(session, version, domain=Domain.SAMD, client=client)

    assert result.irs_written == 0
    assert result.rejected_uncited == 1

    run = session.get(ExtractionRun, result.run_id)
    assert run.rejected_uncited == 1, "the rejection is on the record, not merely absent"

    orphans = session.scalar(
        select(func.count(IR.id))
        .outerjoin(IRCitation, IRCitation.ir_id == IR.id)
        .where(IRCitation.id.is_(None))
    )
    assert orphans == 0


def test_the_database_refuses_an_uncited_ir_even_when_code_does_not(session, source):
    """The invariant is structural, not a convention this service happens to follow.

    Migration 0004's deferred constraint trigger is what makes "an IR without a citation does not
    exist" true of the *database*. Enforcing it only in the extractor would leave it one careless
    ``session.add`` away from being false.
    """
    session.add(
        IR(
            domain_profile=Domain.SAMD,
            statement="citation-free obligation",
            status=IRStatus.DRAFT,
        )
    )
    with pytest.raises(IntegrityError, match="no citation"):
        session.commit()
    session.rollback()


# --- criterion: every clause is classified ----------------------------------------------------


def test_every_clause_is_classified_with_no_unclassified_remainder(session, source):
    """*Every clause in a processed version is either obligation-bearing or excluded with a reason.*

    ADR-0004 decision 6. "2 IRs from 5 clauses" is uninterpretable unless the other clauses are on
    record as examined-and-empty — otherwise it cannot be told apart from 3 missed obligations.
    """
    version = _make_version(
        session, source, raw=_law_xml(ARTICLES), canonical_key=f"{KEY_PREFIX}:coverage"
    )
    path = _clause_path(session, version, "5")

    client = StubLLM({path: [_ir_json("기록을 3년간 보관", cites=[path])]})
    result = extract_version(session, version, domain=Domain.SAMD, client=client)

    clauses = session.scalar(
        select(func.count(Clause.id)).where(Clause.document_version_id == version.id)
    )
    classified = session.scalar(
        select(func.count(ClauseClassification.id))
        .join(Clause, Clause.id == ClauseClassification.clause_id)
        .where(
            Clause.document_version_id == version.id,
            ClauseClassification.domain_profile == Domain.SAMD,
        )
    )
    assert classified == clauses, "no unclassified remainder"
    assert result.obligation_bearing + result.excluded == clauses

    # Excluded rows carry a reason, and more than one kind of reason — a single-reason ledger would
    # pass this test while telling a reviewer nothing.
    reasons = result.exclusion_reasons
    assert reasons, "an excluded clause without a reason is indistinguishable from a skipped one"
    assert {"definition", "delegation", "permissive"} <= set(reasons)

    unreasoned = session.scalar(
        select(func.count(ClauseClassification.id))
        .join(Clause, Clause.id == ClauseClassification.clause_id)
        .where(
            Clause.document_version_id == version.id,
            ClauseClassification.kind == ClassificationKind.EXCLUDED,
            ClauseClassification.exclusion_reason.is_(None),
        )
    )
    assert unreasoned == 0


# --- criterion: provenance --------------------------------------------------------------------


def test_every_ir_carries_its_provenance_and_the_run_pins_temperature(session, source):
    """*Every `irs` row carries a non-null `llm_provider` / `llm_model`.*

    Plus ADR-0017 decision 1: the temperature actually used is on the run, so the determinism claim
    is checkable against evidence rather than against a constant that may since have been edited.
    """
    version = _make_version(
        session, source, raw=_law_xml(ARTICLES), canonical_key=f"{KEY_PREFIX}:prov"
    )
    path = _clause_path(session, version, "5")

    client = StubLLM({path: [_ir_json("보관", cites=[path])]})
    result = extract_version(session, version, domain=Domain.SAMD, client=client)
    assert result.irs_written == 1

    ir = session.scalar(
        select(IR)
        .join(IRCitation, IRCitation.ir_id == IR.id)
        .where(IRCitation.document_version_id == version.id)
    )
    assert ir.llm_provider == "stub"
    assert ir.llm_model == "stub-model"
    assert ir.prompt_version and ir.rule_version
    assert ir.extraction_run_id == result.run_id

    run = session.get(ExtractionRun, result.run_id)
    assert run.temperature == 0.0
    assert run.status is ExtractionRunStatus.COMPLETED
    assert client.temperatures and all(t == 0.0 for t in client.temperatures)


# --- criterion: a draft IR is invisible -------------------------------------------------------


def test_extraction_produces_only_drafts_and_locking_is_what_makes_them_visible(session, source):
    """*A draft IR is invisible to retrieval and impact grading.*

    ADR-0004 decision 4. Nothing in the pipeline writes ``locked``: the transition is a human
    action, which is the whole Part 11 story as much as a quality story.
    """
    version = _make_version(
        session, source, raw=_law_xml(ARTICLES), canonical_key=f"{KEY_PREFIX}:draft"
    )
    path = _clause_path(session, version, "5")

    client = StubLLM({path: [_ir_json("보관", cites=[path]), _ir_json("보고", cites=[path])]})
    extract_version(session, version, domain=Domain.SAMD, client=client)

    statuses = set(
        session.scalars(
            select(IR.status)
            .join(IRCitation, IRCitation.ir_id == IR.id)
            .where(IRCitation.document_version_id == version.id)
        )
    )
    assert statuses == {IRStatus.DRAFT}

    visible = session.scalar(
        select(func.count(IR.id))
        .join(IRCitation, IRCitation.ir_id == IR.id)
        .where(IRCitation.document_version_id == version.id, IR.status == IRStatus.LOCKED)
    )
    assert visible == 0, "nothing downstream may read this version's obligations yet"


# --- criterion: amendments re-derive ----------------------------------------------------------


def test_amending_a_cited_clause_stales_the_ir_and_produces_a_superseding_one(session, source):
    """*Amending a cited clause marks the IR stale and produces a superseding IR, old one intact.*

    ADR-0004 decision 5, end to end: extract → lock → amend → diff → re-derive. The locked IR must
    survive **unchanged** — mutating it in place would silently change the meaning of every mapping
    and answer that already referenced it, while the audit trail still showed one approved record.
    """
    key = f"{KEY_PREFIX}:amend"
    first = _make_version(
        session,
        source,
        raw=_law_xml(ARTICLES),
        canonical_key=key,
        retrieved_at=datetime.now(UTC) - timedelta(days=1),
    )
    path = _clause_path(session, first, "5")

    client = StubLLM({path: [_ir_json("기록을 3년간 보관", cites=[path])]})
    extract_version(session, first, domain=Domain.SAMD, client=client)

    original = session.scalar(
        select(IR)
        .join(IRCitation, IRCitation.ir_id == IR.id)
        .where(IRCitation.document_version_id == first.id)
    )
    original.status = IRStatus.LOCKED
    original.locked_by = uuid.uuid4()
    original.locked_at = datetime.now(UTC)
    session.commit()
    original_id, original_statement = original.id, original.statement

    # The amendment: 3년 → 5년 on the cited article.
    amended = dict(ARTICLES)
    amended["5"] = (
        "기록의 보관) 제조업자는 기록을 5년간 보관하여야 하며, 매년 결과를 보고하여야 한다."
    )
    second = _make_version(session, source, raw=_law_xml(amended), canonical_key=key)

    diff = diff_version(session, second)
    assert diff.citations_superseded == 1
    assert diff.irs_marked_stale == 1, "flagging must not wait on a model being reachable"

    session.refresh(original)
    assert original.status is IRStatus.STALE
    assert original.stale_since is not None

    new_path = _clause_path(session, second, "5")
    rederiver = StubLLM({new_path: [_ir_json("기록을 5년간 보관", cites=[new_path])]})
    rederived = rederive_version(session, second, client=rederiver)

    assert rederived.stale_seen == 1
    assert rederived.superseded == 1
    assert rederived.irs_written == 1

    successor = session.scalar(select(IR).where(IR.supersedes_ir_id == original_id))
    assert successor is not None
    assert successor.status is IRStatus.DRAFT, "a re-derived IR is a proposal, not an approval"
    assert "5년" in successor.statement

    # The old IR is retained, frozen, and still says what it said.
    frozen = session.get(IR, original_id)
    assert frozen is not None
    assert frozen.status is IRStatus.SUPERSEDED
    assert frozen.statement == original_statement
    assert frozen.locked_at is not None, "the signature on the original survives"

    # Its citation is flagged, not rewritten — the original evidence stays resolvable.
    citation = session.scalar(select(IRCitation).where(IRCitation.ir_id == original_id))
    assert citation.document_version_id == first.id
    assert citation.superseded_at is not None


def test_a_removed_clause_leaves_its_ir_stale_for_a_human(session, source):
    """ "This obligation no longer exists" is the highest-impact thing an amendment can say.

    It is not resolved by a sweep. The IR stays ``stale`` and visible as work rather than being
    quietly superseded with no successor.
    """
    key = f"{KEY_PREFIX}:removed"
    first = _make_version(
        session,
        source,
        raw=_law_xml(ARTICLES),
        canonical_key=key,
        retrieved_at=datetime.now(UTC) - timedelta(days=1),
    )
    path = _clause_path(session, first, "5")
    extract_version(
        session,
        first,
        domain=Domain.SAMD,
        client=StubLLM({path: [_ir_json("보관", cites=[path])]}),
    )
    ir_id = session.scalar(
        select(IR.id)
        .join(IRCitation, IRCitation.ir_id == IR.id)
        .where(IRCitation.document_version_id == first.id)
    )

    without_five = {k: v for k, v in ARTICLES.items() if k != "5"}
    second = _make_version(session, source, raw=_law_xml(without_five), canonical_key=key)
    diff_version(session, second)

    assert session.get(IR, ir_id).status is IRStatus.STALE

    rederived = rederive_version(session, second, client=StubLLM())
    assert rederived.superseded == 0
    assert rederived.unresolved == 1
    assert session.get(IR, ir_id).status is IRStatus.STALE, "left for an RA, not auto-resolved"


# --- criterion: the domain branch is a rule set, not a code path -------------------------------


def test_a_document_claimed_by_both_cells_extracts_once_per_domain(session, source, cells):
    """ADR-0004 decision 3 — same tables, same stages, one run per rule set.

    인체적용제품의 위해성평가에 관한 규정 is claimed by both gated cells for real. A clause bearing
    a duty under the SaMD taxonomy may bear none under the Cosmetic one, so the two readings get
    separate runs, separate classifications and separate IRs.
    """
    version = _make_version(
        session,
        source,
        raw=_law_xml(ARTICLES),
        canonical_key=f"{KEY_PREFIX}:bothcells",
        claim=[cells["mfds_samd"], cells["mfds_cosmetic"]],
    )
    path = _clause_path(session, version, "5")

    assert domains_for(session, version.document_id) == [Domain.COSMETIC, Domain.SAMD]

    for domain in (Domain.SAMD, Domain.COSMETIC):
        extract_version(
            session,
            version,
            domain=domain,
            client=StubLLM({path: [_ir_json("보관", cites=[path])]}),
        )

    profiles = sorted(
        session.scalars(
            select(ExtractionRun.domain_profile).where(
                ExtractionRun.document_version_id == version.id
            )
        ),
        key=lambda d: d.value,
    )
    assert profiles == [Domain.COSMETIC, Domain.SAMD]

    # One classification per (clause, domain) — the two readings never share a row.
    per_domain = dict(
        session.execute(
            select(ClauseClassification.domain_profile, func.count())
            .join(Clause, Clause.id == ClauseClassification.clause_id)
            .where(Clause.document_version_id == version.id)
            .group_by(ClauseClassification.domain_profile)
        ).all()
    )
    clauses = session.scalar(
        select(func.count(Clause.id)).where(Clause.document_version_id == version.id)
    )
    assert per_domain == {Domain.SAMD: clauses, Domain.COSMETIC: clauses}


# --- idempotency -------------------------------------------------------------------------------


def test_re_extraction_replaces_drafts_and_never_touches_a_locked_ir(session, source):
    """Re-running the extractor is not a reason to destroy a human's signature.

    ADR-0015 makes re-running a derived stage routine; a routine operation must not degrade the
    record. Drafts are unreviewed proposals and are replaced; a locked IR is evidence and is not.
    """
    version = _make_version(
        session, source, raw=_law_xml(ARTICLES), canonical_key=f"{KEY_PREFIX}:idem"
    )
    path = _clause_path(session, version, "5")

    extract_version(
        session,
        version,
        domain=Domain.SAMD,
        client=StubLLM(
            {path: [_ir_json("첫 번째", cites=[path]), _ir_json("두 번째", cites=[path])]}
        ),
    )
    irs = list(
        session.scalars(
            select(IR)
            .join(IRCitation, IRCitation.ir_id == IR.id)
            .where(IRCitation.document_version_id == version.id)
        )
    )
    assert len(irs) == 2

    keeper = irs[0]
    keeper.status = IRStatus.LOCKED
    keeper.locked_at = datetime.now(UTC)
    session.commit()
    keeper_id, keeper_statement = keeper.id, keeper.statement

    extract_version(
        session,
        version,
        domain=Domain.SAMD,
        client=StubLLM({path: [_ir_json("세 번째", cites=[path])]}),
    )

    surviving = {
        ir.statement: ir.status
        for ir in session.scalars(
            select(IR)
            .join(IRCitation, IRCitation.ir_id == IR.id)
            .where(IRCitation.document_version_id == version.id)
        )
    }
    assert surviving == {keeper_statement: IRStatus.LOCKED, "세 번째": IRStatus.DRAFT}
    assert session.get(IR, keeper_id).status is IRStatus.LOCKED


def test_a_human_classification_survives_a_re_run(session, source):
    """An RA's disagreement with the agent is a judgement, not a cached computation."""
    version = _make_version(
        session, source, raw=_law_xml(ARTICLES), canonical_key=f"{KEY_PREFIX}:override"
    )
    extract_version(session, version, domain=Domain.SAMD, client=StubLLM())

    definition = session.scalar(
        select(ClauseClassification)
        .join(Clause, Clause.id == ClauseClassification.clause_id)
        .where(
            Clause.document_version_id == version.id,
            Clause.clause_path.like("%제2조"),
            ClauseClassification.domain_profile == Domain.SAMD,
        )
    )
    reviewer = uuid.uuid4()
    definition.kind = ClassificationKind.OBLIGATION_BEARING
    definition.exclusion_reason = None
    definition.classified_by = reviewer
    session.commit()

    extract_version(session, version, domain=Domain.SAMD, client=StubLLM())

    session.refresh(definition)
    assert definition.classified_by == reviewer
    assert definition.kind is ClassificationKind.OBLIGATION_BEARING


# --- concurrency: a redelivered task must not clear a live run's drafts ------------------------


def _fake_live_run(session, version, *, heartbeat_age: timedelta) -> ExtractionRun:
    """A row claiming to be running this version, with a heartbeat of a chosen age."""
    run = ExtractionRun(
        document_version_id=version.id,
        domain_profile=Domain.SAMD,
        rule_version="test",
        prompt_version="test",
        llm_provider="stub",
        llm_model="stub",
        temperature=0.0,
        status=ExtractionRunStatus.RUNNING,
        started_at=datetime.now(UTC) - heartbeat_age,
        heartbeat_at=datetime.now(UTC) - heartbeat_age,
    )
    session.add(run)
    session.commit()
    return run


def test_a_second_extraction_over_a_live_run_is_refused(session, source):
    """A duplicate does not have to arrive through the API, so the API cannot be the only guard.

    Redis redelivers any task still running at the broker's visibility timeout while the original
    is still executing. On 2026-08-27 that copy ran ``_clear_previous_drafts`` and destroyed 89
    drafts the live run had committed. The refusal therefore lives in ``extract_version``, where
    every path to an extraction converges.
    """
    version = _make_version(
        session, source, raw=_law_xml(ARTICLES), canonical_key=f"{KEY_PREFIX}:concurrent"
    )
    path = _clause_path(session, version, "5")
    client = StubLLM({path: [_ir_json("기록을 3년간 보관", cites=[path])]})

    first = extract_version(session, version, domain=Domain.SAMD, client=client)
    assert first.irs_written == 1
    drafts = _draft_ids(session, version)
    assert len(drafts) == 1

    live = _fake_live_run(session, version, heartbeat_age=timedelta(minutes=1))
    second = extract_version(session, version, domain=Domain.SAMD, client=client)

    assert second.error is not None, "a concurrent run must refuse, not proceed"
    assert second.run_id == live.id, "the refusal names the run it deferred to"
    assert second.irs_written == 0
    assert _draft_ids(session, version) == drafts, "the live run's drafts must survive"


def test_a_run_without_a_pulse_does_not_block_a_re_run(session, source):
    """The guard asks for a heartbeat, not for a status.

    Guarding on ``running`` alone would make a worker killed mid-corpus permanent: the row says
    ``running`` forever and the version becomes unextractable. The dead row is passed over.
    """
    version = _make_version(
        session, source, raw=_law_xml(ARTICLES), canonical_key=f"{KEY_PREFIX}:pulseless"
    )
    path = _clause_path(session, version, "5")
    client = StubLLM({path: [_ir_json("기록을 3년간 보관", cites=[path])]})

    _fake_live_run(
        session, version, heartbeat_age=EXTRACTION_HEARTBEAT_STALE_AFTER + timedelta(minutes=1)
    )
    result = extract_version(session, version, domain=Domain.SAMD, client=client)

    assert result.error is None
    assert result.irs_written == 1


def _draft_ids(session, version) -> set[uuid.UUID]:
    return set(
        session.scalars(
            select(IR.id)
            .join(IRCitation, IRCitation.ir_id == IR.id)
            .where(IRCitation.document_version_id == version.id, IR.status == IRStatus.DRAFT)
        )
    )
