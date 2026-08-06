"""Phase 1.1 acceptance criteria, against the real stack.

    docker compose --profile app up -d
    docker compose run --rm migrate
    STAGE=test REGOPS_DB_NAME=regops_test docker compose run --rm regulation \
        python -m pytest tests/integration -q

Real Postgres and real MinIO; the *network* is stubbed, because every criterion here is about what
the pipeline does with a response rather than whether law.go.kr is reachable from CI.

Each test names the criterion it covers from
[phase1.1](../../../../docs/plan/phase1.1_normalization.md) § Acceptance criteria.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import delete, func, select

from app.diff import diff_version
from app.models import (
    IR,
    Cell,
    ChangeEvent,
    Clause,
    ClauseDiff,
    Document,
    DocumentCell,
    DocumentVersion,
    IRCitation,
    Source,
    StructureDriftAlert,
)
from app.parse import parse_version
from regops_shared.constants import (
    ChangeKind,
    ClauseKind,
    DocType,
    Domain,
    DriftSignal,
    IRStatus,
    SourceBlock,
    SourceTier,
)
from regops_shared.db import sync_session
from regops_shared.storage import archive_bytes

pytestmark = pytest.mark.integration

KEY_PREFIX = "test:phase11"
SLUG = "test.phase11.source"


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
            citations = select(IRCitation.ir_id).where(IRCitation.document_version_id.in_(versions))
            ir_ids = list(session.scalars(citations))
            session.execute(delete(IRCitation).where(IRCitation.document_version_id.in_(versions)))
            if ir_ids:
                session.execute(delete(IR).where(IR.id.in_(ir_ids)))
            diffs = select(ClauseDiff.id).where(ClauseDiff.to_version_id.in_(versions))
            session.execute(delete(ChangeEvent).where(ChangeEvent.clause_diff_id.in_(diffs)))
            session.execute(delete(ClauseDiff).where(ClauseDiff.to_version_id.in_(versions)))
            session.execute(delete(ClauseDiff).where(ClauseDiff.from_version_id.in_(versions)))
            session.execute(delete(Clause).where(Clause.document_version_id.in_(versions)))
        session.execute(delete(DocumentCell).where(DocumentCell.document_id.in_(ids)))
        session.execute(delete(DocumentVersion).where(DocumentVersion.document_id.in_(ids)))
        session.execute(delete(Document).where(Document.parent_document_id.in_(ids)))
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
        cell_id=cells["mfds_cosmetic"],
        block=SourceBlock.PRIMARY_LAWS,
        ordinal=1,
        title="phase 1.1 fixture",
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


def _law_xml(*, articles: str, effective: str = "20260402", addendum: str = "") -> bytes:
    body = addendum or (
        "<부칙><부칙단위><부칙공포일자>20250401</부칙공포일자>"
        "<부칙내용>제1조(시행일) 이 법은 공포 후 1년이 경과한 날부터 시행한다.</부칙내용>"
        "</부칙단위></부칙>"
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<법령>
  <기본정보><법령ID>002015</법령ID><법종구분>법률</법종구분>
    <법령명_한글>테스트법</법령명_한글><공포일자>20250401</공포일자>
    <시행일자>{effective}</시행일자></기본정보>
  <조문>{articles}</조문>
  {body}
</법령>
""".encode()


def _article(
    number: str, text: str, *, key: str = "", moved_to: str = "", effective: str = "20260402"
) -> str:
    """``조문시행일자`` defaults to the version's own date, which is what the corpus actually does —
    it is constant per document across all nine gated 법령 (ADR-0016)."""
    return (
        f'<조문단위 조문키="{key or f"000{number}001"}">'
        f"<조문번호>{number}</조문번호><조문여부>조문</조문여부>"
        f"<조문시행일자>{effective}</조문시행일자>"
        f"<조문이동이후>{moved_to}</조문이동이후>"
        f"<조문내용>제{number}조({text}) {text} 내용입니다.</조문내용>"
        f"</조문단위>"
    )


def _make_version(
    session,
    source: Source,
    *,
    raw: bytes,
    canonical_key: str,
    doc_type: DocType = DocType.LAW,
    retrieved_at: datetime | None = None,
    claim: list[uuid.UUID] | None = None,
    parent_id: uuid.UUID | None = None,
) -> DocumentVersion:
    """Stand in for what 1.0's ingest stage leaves behind: an archived blob and a version row."""
    document = session.scalar(select(Document).where(Document.canonical_key == canonical_key))
    if document is None:
        document = Document(
            canonical_key=canonical_key,
            title=canonical_key,
            doc_type=doc_type,
            source_id=source.id,
            parent_document_id=parent_id,
            annex_no=canonical_key.partition("#")[2] or None,
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
    return version


# --- criterion: both domains parse through one pipeline ---------------------------------------


def test_both_domains_parse_through_one_pipeline_with_no_domain_branch(session, source, cells):
    """*화장품법 and 의료기기법 both parse to clauses through one pipeline, no domain branch.*

    The two versions differ only in which cell claims them. Same profile, same clause kinds, same
    path shape — which is ADR-0002 decision 3's claim, exercised rather than asserted.
    """
    articles = _article("1", "목적") + _article("2", "정의")

    cosmetic = _make_version(
        session,
        source,
        raw=_law_xml(articles=articles),
        canonical_key=f"{KEY_PREFIX}:cosmetic",
        claim=[cells["mfds_cosmetic"]],
    )
    samd = _make_version(
        session,
        source,
        raw=_law_xml(articles=articles, effective="20260701"),
        canonical_key=f"{KEY_PREFIX}:samd",
        claim=[cells["mfds_samd"]],
    )

    first = parse_version(session, cosmetic)
    second = parse_version(session, samd)

    assert first.ok and second.ok
    assert first.profile == second.profile == "law_structured"
    assert first.clauses_written == second.clauses_written

    paths = {
        version.id: sorted(
            session.scalars(
                select(Clause.clause_path).where(Clause.document_version_id == version.id)
            )
        )
        for version in (cosmetic, samd)
    }
    assert paths[cosmetic.id] == paths[samd.id]


# --- criterion: renumbering is never delete + add ---------------------------------------------


def test_a_renumbered_clause_reports_renumbered_not_delete_plus_add(session, source):
    """*A renumbered-but-unchanged clause reports ``renumbered``, never delete + add.*

    The move is taken from the authority's own ``조문이동이후`` — for law.go.kr the move is stated,
    not inferred, so ``similarity`` stays null.
    """
    before = _make_version(
        session,
        source,
        raw=_law_xml(
            articles=_article("5", "신고", key="0005001", moved_to="0007001")
            + _article("6", "등록", key="0006001")
        ),
        canonical_key=f"{KEY_PREFIX}:renumber",
        retrieved_at=datetime.now(UTC) - timedelta(days=1),
    )
    parse_version(session, before)
    diff_version(session, before)

    after = _make_version(
        session,
        source,
        raw=_law_xml(
            articles=_article("6", "등록", key="0006001") + _article("7", "신고", key="0007001")
        ),
        canonical_key=f"{KEY_PREFIX}:renumber",
    )
    parse_version(session, after)
    result = diff_version(session, after)

    kinds = {
        row.change_kind
        for row in session.scalars(select(ClauseDiff).where(ClauseDiff.to_version_id == after.id))
    }
    assert ChangeKind.RENUMBERED in kinds
    assert ChangeKind.REMOVED not in kinds
    assert ChangeKind.ADDED not in kinds

    renumber = session.scalar(
        select(ClauseDiff).where(
            ClauseDiff.to_version_id == after.id,
            ClauseDiff.change_kind == ChangeKind.RENUMBERED,
        )
    )
    assert renumber.from_clause_path == "제5조"
    assert renumber.clause_path == "제7조"
    assert renumber.match_basis == "authority"
    assert renumber.similarity is None
    assert result.counts.get("renumbered") == 1


def test_a_renumber_without_an_authority_signal_falls_back_to_content(session, source):
    """Sources exposing no move signal — annex rows, 고시 text, Tier C — still must not report a
    renumber as delete + add."""
    before = _make_version(
        session,
        source,
        raw=_law_xml(articles=_article("5", "신고", key="") + _article("6", "등록", key="")),
        canonical_key=f"{KEY_PREFIX}:similarity",
        retrieved_at=datetime.now(UTC) - timedelta(days=1),
    )
    parse_version(session, before)
    diff_version(session, before)

    # Same text, different 조 number, and no 조문이동 fields at all.
    renumbered = (
        '<조문단위 조문키=""><조문번호>9</조문번호><조문여부>조문</조문여부>'
        "<조문시행일자>20260402</조문시행일자>"
        "<조문내용>제5조(신고) 신고 내용입니다.</조문내용></조문단위>"
    )
    after = _make_version(
        session,
        source,
        raw=_law_xml(articles=_article("6", "등록", key="") + renumbered),
        canonical_key=f"{KEY_PREFIX}:similarity",
    )
    parse_version(session, after)
    diff_version(session, after)

    row = session.scalar(
        select(ClauseDiff).where(
            ClauseDiff.to_version_id == after.id,
            ClauseDiff.change_kind == ChangeKind.RENUMBERED,
        )
    )
    assert row is not None
    assert row.match_basis == "content_hash"
    assert row.from_clause_path == "제5조"


# --- criterion: annex row round-trips as a Clause ---------------------------------------------


ANNEX_XML = """<?xml version="1.0" encoding="UTF-8"?>
<AdmRulService>
  <행정규칙기본정보><행정규칙명>안전기준</행정규칙명><시행일자>20260318</시행일자>
  </행정규칙기본정보>
  <조문내용>제1조(목적) 목적.</조문내용>
  <별표><별표단위>
    <별표번호>0002</별표번호><별표가지번호>00</별표가지번호>
    <별표구분>별표</별표구분><별표제목>사용상의 제한이 필요한 원료</별표제목>
    <별표내용>[별표 2]

* 보존제 성분

┌──────────┬─────────┬───────┐
│원    료    명      │사 용 한 도       │CAS No.       │
├──────────┼─────────┼───────┤
│글루타랄(펜탄       │0.1%              │111-30-8      │
│-1,5-디알)          │                  │              │
├──────────┼─────────┼───────┤
│페녹시에탄올        │1.0%              │122-99-6      │
└──────────┴─────────┴───────┘
</별표내용>
  </별표단위></별표>
</AdmRulService>
"""


def test_an_annex_limit_table_row_round_trips_as_a_citable_clause(session, source):
    """*An annex limit-table row round-trips as a ``Clause`` and is addressable by ``clause_path``.*

    **This is the phase 1.1 falsifier** (ADR-0004 decision 3). Failing it falsifies the
    shared-pipeline claim that Phase 2's six-cell build rests on.
    """
    body = _make_version(
        session,
        source,
        raw=ANNEX_XML.encode(),
        canonical_key=f"{KEY_PREFIX}:annexparent",
        doc_type=DocType.NOTICE,
    )
    annex = _make_version(
        session,
        source,
        raw=ANNEX_XML.encode(),
        canonical_key=f"{KEY_PREFIX}:annexparent#별표2",
        doc_type=DocType.ANNEX,
        parent_id=body.document_id,
    )

    assert parse_version(session, annex).ok

    row = session.scalar(
        select(Clause).where(
            Clause.document_version_id == annex.id,
            Clause.clause_path == "별표2/표1/행1",
        )
    )
    assert row is not None, "the falsifier fired: an annex row is not addressable by clause_path"
    assert row.kind is ClauseKind.TABLE_ROW
    assert row.path_segments == ["별표2", "표1", "행1"]
    assert row.row_columns["원료명"] == "글루타랄(펜탄-1,5-디알)"
    assert row.row_columns["CAS No."] == "111-30-8"

    # Exact-match lookup on the identifier column — the query shape ADR-0006 decision 3 requires.
    found = session.scalar(
        select(Clause).where(
            Clause.document_version_id == annex.id,
            Clause.row_columns["CAS No."].astext == "122-99-6",
        )
    )
    assert found is not None
    assert found.clause_path == "별표2/표1/행2"


# --- criterion: a parse yielding zero clauses fails closed ------------------------------------


def test_zero_clauses_raises_drift_creates_no_version_and_emits_no_change_event(session, source):
    """*A parse yielding zero clauses raises drift, creates no version, and emits no change event.*

    The version is **removed**, keeping the invariant that a ``DocumentVersion`` which exists has
    clauses and is citable. The archived blob is untouched — it is write-once, and it plus the
    fetch observation are what prove what came back.
    """
    version = _make_version(
        session,
        source,
        raw=_law_xml(articles=""),
        canonical_key=f"{KEY_PREFIX}:empty",
    )
    version_id = version.id
    object_key = version.raw_object_key

    result = parse_version(session, version)

    assert result.drift is DriftSignal.ZERO_CLAUSES
    assert session.get(DocumentVersion, version_id) is None
    assert not session.scalars(select(Clause).where(Clause.document_version_id == version_id)).all()
    assert not session.scalars(
        select(ClauseDiff).where(ClauseDiff.to_version_id == version_id)
    ).all()

    alert = session.scalar(
        select(StructureDriftAlert).where(
            StructureDriftAlert.source_id == source.id,
            StructureDriftAlert.signal == DriftSignal.ZERO_CLAUSES,
        )
    )
    assert alert is not None
    assert alert.resolved_at is None

    # The evidence survives even though the version did not.
    from regops_shared.storage import read_archived

    assert read_archived(object_key)


def test_a_clause_count_collapse_raises_drift(session, source):
    """A count that moves beyond the threshold is structure drift, not an amendment — ADR-0003
    decision 6's second parse-stage signal."""
    articles = "".join(_article(str(n), f"조문{n}") for n in range(1, 11))
    first = _make_version(
        session,
        source,
        raw=_law_xml(articles=articles),
        canonical_key=f"{KEY_PREFIX}:collapse",
        retrieved_at=datetime.now(UTC) - timedelta(days=1),
    )
    assert parse_version(session, first).ok

    second = _make_version(
        session,
        source,
        raw=_law_xml(articles=_article("1", "조문1")),
        canonical_key=f"{KEY_PREFIX}:collapse",
    )
    second_id = second.id
    result = parse_version(session, second)

    assert result.drift is DriftSignal.CLAUSE_COUNT_DELTA
    assert session.get(DocumentVersion, second_id) is None


# --- criterion: 시행예정 does not displace 현행 -----------------------------------------------


def test_a_pending_version_does_not_displace_the_in_force_one(session, source):
    """*A 시행예정 version is ingested with a future ``effective_date`` and does not displace 현행 —
    a query for the current text still returns the in-force version.*

    There is no status flag: in force is ``effective_date <= today`` (ADR-0016 decision 6), so the
    date answers the question and keeps answering it as time passes.
    """
    current = _make_version(
        session,
        source,
        raw=_law_xml(articles=_article("1", "목적") + _article("2", "정의"), effective="20260402"),
        canonical_key=f"{KEY_PREFIX}:pending",
        retrieved_at=datetime.now(UTC) - timedelta(days=1),
    )
    assert parse_version(session, current).ok

    pending = _make_version(
        session,
        source,
        raw=_law_xml(
            articles=_article("1", "목적", effective="20291231")
            + _article("2", "정의개정", effective="20291231"),
            effective="20291231",
        ),
        canonical_key=f"{KEY_PREFIX}:pending",
    )
    assert parse_version(session, pending).ok

    session.refresh(current)
    session.refresh(pending)
    assert current.effective_date == date(2026, 4, 2)
    assert pending.effective_date == date(2029, 12, 31)

    today = date.today()
    in_force = session.scalar(
        select(DocumentVersion)
        .where(
            DocumentVersion.document_id == current.document_id,
            DocumentVersion.effective_date <= today,
        )
        .order_by(DocumentVersion.effective_date.desc())
        .limit(1)
    )
    assert in_force.id == current.id, "the pending version displaced 현행"


def test_staged_dates_land_in_the_phrase_not_on_clauses(session, source):
    """*One MST carrying three 시행일자 produces exactly one version, with the earliest date at
    version level* — **and the remainder in ``effective_date_phrase``, not on clauses.**

    ADR-0016 corrects the second half of this criterion. 조문시행일자 is constant per document
    across the whole gated corpus, and the 부칙's staged dates are conditional on the addressee's
    revenue, so no clause-level date is correct.
    """
    addendum = (
        "<부칙><부칙단위><부칙공포일자>20251230</부칙공포일자><부칙내용>"
        "제1조(시행일) 이 법은 공포 후 1년이 경과한 날부터 시행한다. "
        "다만, 제5조의2의 개정규정은 2028년 1월 1일부터, "
        "제4조의3의 개정규정은 2029년 1월 1일부터 시행한다."
        "</부칙내용></부칙단위></부칙>"
    )
    version = _make_version(
        session,
        source,
        raw=_law_xml(
            articles=_article("1", "목적", effective="20261231"),
            effective="20261231",
            addendum=addendum,
        ),
        canonical_key=f"{KEY_PREFIX}:staged",
    )
    assert parse_version(session, version).ok
    session.refresh(version)

    assert version.effective_date == date(2026, 12, 31)  # the earliest
    assert "2028년 1월 1일" in version.effective_date_phrase
    assert "2029년 1월 1일" in version.effective_date_phrase

    clause_dates = session.scalars(
        select(Clause.effective_date).where(Clause.document_version_id == version.id)
    ).all()
    assert all(value is None for value in clause_dates)


# --- criterion: fan-out reaches every claiming cell and no others -----------------------------


def test_fan_out_reaches_every_claiming_cell(session, source, cells):
    """*Fan-out reaches every claiming cell and no others — verified against a synthetic multi-cell
    fixture.*

    Synthetic on purpose: the two gated cells share no *regulation*, and the FD&C Act — the natural
    M:N case — is FDA, first ingested in phase 2.0. Cell isolation is a CLAUDE.md non-negotiable
    test, so Phase 1 builds the fixture rather than deferring the test.
    """
    key = f"{KEY_PREFIX}:shared"
    both = [cells["mfds_cosmetic"], cells["mfds_samd"]]

    first = _make_version(
        session,
        source,
        raw=_law_xml(articles=_article("1", "목적")),
        canonical_key=key,
        claim=both,
        retrieved_at=datetime.now(UTC) - timedelta(days=1),
    )
    parse_version(session, first)
    diff_version(session, first)

    second = _make_version(
        session,
        source,
        raw=_law_xml(articles=_article("1", "목적개정")),
        canonical_key=key,
        claim=both,
    )
    parse_version(session, second)
    result = diff_version(session, second)

    diffs = session.scalars(
        select(ClauseDiff.id).where(ClauseDiff.to_version_id == second.id)
    ).all()
    assert diffs, "an amendment produced no diff"

    events = session.scalars(select(ChangeEvent).where(ChangeEvent.clause_diff_id.in_(diffs))).all()
    assert {event.cell_id for event in events} == set(both)
    assert result.change_events == len(diffs) * 2


def test_a_single_cell_document_does_not_fan_out_to_the_other_gated_cell(session, source, cells):
    """*A single-cell document does not fan out to the other gated cell* — the negative half."""
    key = f"{KEY_PREFIX}:isolated"
    first = _make_version(
        session,
        source,
        raw=_law_xml(articles=_article("1", "목적")),
        canonical_key=key,
        claim=[cells["mfds_cosmetic"]],
        retrieved_at=datetime.now(UTC) - timedelta(days=1),
    )
    parse_version(session, first)
    diff_version(session, first)

    second = _make_version(
        session,
        source,
        raw=_law_xml(articles=_article("1", "목적개정")),
        canonical_key=key,
        claim=[cells["mfds_cosmetic"]],
    )
    parse_version(session, second)
    diff_version(session, second)

    diffs = session.scalars(
        select(ClauseDiff.id).where(ClauseDiff.to_version_id == second.id)
    ).all()
    events = session.scalars(select(ChangeEvent).where(ChangeEvent.clause_diff_id.in_(diffs))).all()

    assert events
    assert {event.cell_id for event in events} == {cells["mfds_cosmetic"]}
    assert cells["mfds_samd"] not in {event.cell_id for event in events}


def test_the_first_version_of_a_document_is_a_baseline_not_an_amendment(session, source):
    """A whole statute reported as thousands of additions would drown the coverage signal."""
    version = _make_version(
        session,
        source,
        raw=_law_xml(articles=_article("1", "목적") + _article("2", "정의")),
        canonical_key=f"{KEY_PREFIX}:baseline",
    )
    parse_version(session, version)
    result = diff_version(session, version)

    assert result.baseline
    assert result.change_events == 0
    assert not session.scalars(
        select(ClauseDiff).where(ClauseDiff.to_version_id == version.id)
    ).all()


# --- criterion: superseded citations ----------------------------------------------------------


def test_amending_a_cited_clause_flags_it_superseded_and_leaves_the_text_resolvable(
    session, source
):
    """*Amending a cited clause flags the citation superseded and leaves its text resolvable.*

    The citation is **never** rewritten (ADR-0002 decision 4): repointing it would silently change
    the evidence behind an obligation an RA already locked.
    """
    key = f"{KEY_PREFIX}:cited"
    first = _make_version(
        session,
        source,
        raw=_law_xml(articles=_article("8", "안전기준")),
        canonical_key=key,
        retrieved_at=datetime.now(UTC) - timedelta(days=1),
    )
    parse_version(session, first)
    diff_version(session, first)

    ir = IR(
        domain_profile=Domain.COSMETIC,
        statement="안전기준을 준수하여야 한다",
        status=IRStatus.LOCKED,
    )
    session.add(ir)
    session.flush()
    citation = IRCitation(
        ir_id=ir.id,
        document_id=first.document_id,
        document_version_id=first.id,
        clause_path="제8조",
        effective_date=first.effective_date,
    )
    session.add(citation)
    session.commit()

    second = _make_version(
        session,
        source,
        raw=_law_xml(articles=_article("8", "안전기준개정")),
        canonical_key=key,
    )
    parse_version(session, second)
    result = diff_version(session, second)

    session.refresh(citation)
    assert result.citations_superseded == 1
    assert citation.superseded_at is not None
    assert citation.superseded_by_diff_id is not None

    # Never rewritten: still pointing at the version it was made against.
    assert citation.document_version_id == first.id
    assert citation.clause_path == "제8조"

    # And the cited text is still resolvable.
    original = session.scalar(
        select(Clause).where(Clause.document_version_id == first.id, Clause.clause_path == "제8조")
    )
    assert original is not None
    assert "안전기준" in original.text


# --- re-parse is idempotent -------------------------------------------------------------------


def test_an_index_shift_is_not_a_change(session, source):
    """Inserting one article shifts every ordinal below it. Those are not changes.

    `ordinal` is reading order, not identity — in a numbered hierarchy the *path* is the position.
    Emitting an index shift as `moved` produced **1,209 change events for one 화장품법 amendment
    that had 37 real edits**, which is the false-alert failure ADR-0002 decision 7 exists to
    prevent.
    """
    key = f"{KEY_PREFIX}:shift"
    before = _make_version(
        session,
        source,
        raw=_law_xml(articles="".join(_article(str(n), f"조문{n}") for n in range(2, 8))),
        canonical_key=key,
        retrieved_at=datetime.now(UTC) - timedelta(days=1),
    )
    parse_version(session, before)
    diff_version(session, before)

    # Prepend 제1조: every following clause keeps its path and text but shifts index by one.
    after = _make_version(
        session,
        source,
        raw=_law_xml(
            articles=_article("1", "신설")
            + "".join(_article(str(n), f"조문{n}") for n in range(2, 8))
        ),
        canonical_key=key,
    )
    parse_version(session, after)
    result = diff_version(session, after)

    assert result.counts.get("moved", 0) == 0, "an index shift was reported as a move"
    assert result.counts.get("modified", 0) == 0
    assert result.counts.get("added") == 1  # only the genuinely new article
    assert result.change_events == 1


def test_reparsing_a_version_invalidates_the_diffs_derived_from_it(session, source):
    """A re-parse replaces the clauses a diff was computed over.

    ``clause_diffs`` references them ``ON DELETE SET NULL``, so without invalidation a re-parse
    leaves diffs whose endpoints are null — describing a parse that no longer exists, with live
    `ChangeEvent` rows still hanging off them. Observed for real: re-parsing the corpus orphaned
    2,373 of them. ADR-0015 makes re-parsing routine, so it must not degrade the change history.
    """
    key = f"{KEY_PREFIX}:reparse_diffs"
    first = _make_version(
        session,
        source,
        raw=_law_xml(articles=_article("1", "목적")),
        canonical_key=key,
        retrieved_at=datetime.now(UTC) - timedelta(days=1),
    )
    parse_version(session, first)
    diff_version(session, first)

    second = _make_version(
        session,
        source,
        raw=_law_xml(articles=_article("1", "목적개정")),
        canonical_key=key,
    )
    parse_version(session, second)
    diff_version(session, second)

    diffs = session.scalars(select(ClauseDiff).where(ClauseDiff.to_version_id == second.id)).all()
    assert diffs and all(d.from_clause_id and d.to_clause_id for d in diffs)

    # Re-parse the *earlier* version: the successor's diff points at clauses about to be replaced.
    result = parse_version(session, first)
    assert result.successor_to_rediff == second.id, "the successor was not flagged for re-diff"

    orphaned = session.scalars(
        select(ClauseDiff).where(
            ClauseDiff.to_version_id == second.id, ClauseDiff.from_clause_id.is_(None)
        )
    ).all()
    assert not orphaned, "a re-parse left diffs pointing at deleted clauses"

    # Healing it re-creates the diff and its change events against the fresh clauses.
    diff_version(session, second)
    healed = session.scalars(select(ClauseDiff).where(ClauseDiff.to_version_id == second.id)).all()
    assert healed and all(d.from_clause_id and d.to_clause_id for d in healed)


def test_reparsing_a_version_replaces_its_clauses_rather_than_duplicating_them(session, source):
    """ADR-0015 makes a profile improvement a re-run over the archive. That is only true if the
    re-run is idempotent."""
    version = _make_version(
        session,
        source,
        raw=_law_xml(articles=_article("1", "목적") + _article("2", "정의")),
        canonical_key=f"{KEY_PREFIX}:reparse",
    )
    first = parse_version(session, version)
    second = parse_version(session, version)

    count = session.scalar(
        select(func.count(Clause.id)).where(Clause.document_version_id == version.id)
    )
    assert first.clauses_written == second.clauses_written == count
