"""Phase 1.3 acceptance criteria, against the real stack.

    docker compose --profile app up -d
    REGOPS_DB_NAME=regops_test docker compose run --rm migrate
    STAGE=test REGOPS_DB_NAME=regops_test docker compose run --rm assistant \
        python -m pytest tests/integration -q

Real Postgres with pgvector, real HNSW index, real SQL. **The LLM is stubbed**, and that is not a
shortcut: every criterion here is about what the pipeline does with a model's answer — refuse it,
reject its citation, fail it at verification, or freeze it on amendment — none of which is a claim
about how well a given model reads Korean. Model quality is measured against the golden set in
phase 1.6, per domain, where it belongs.

The fixtures import `regulation`'s models directly, which service code may never do. A test is not
a service: it is building the world the service will read, and going through raw SQL to do it would
make the fixture harder to read without making the boundary any more real.

Each test names the criterion it covers from
[phase1.3](../../../../docs/plan/phase1.3_retrieval_qa.md) § Acceptance criteria.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import delete, select

from app.ask import ask
from app.embedding import embed_version
from app.models import Answer, AnswerCitation, ClauseEmbedding, Query, VerificationResult
from app.retrieval import retrieve
from app.store import cell_ids_for, versions_in_scope
from app.supersede import supersede_for_version
from regops_shared.constants import (
    EMBEDDING_DIM,
    AnswerStatus,
    ChangeKind,
    ClauseKind,
    DocType,
    NoAnswerReason,
    VerificationVerdict,
)
from regops_shared.db import sync_session
from regops_shared.llm import Completion, LLMClient
from regops_shared.models import (
    Cell,
    Clause,
    ClauseDiff,
    Document,
    DocumentCell,
    DocumentVersion,
)

pytestmark = pytest.mark.integration

KEY_PREFIX = "test:phase13"
TODAY = date(2026, 8, 11)


# --- the stub model ---------------------------------------------------------------------------


class StubLLM(LLMClient):
    """Scripted generation, scripted verification, and a deterministic embedding.

    The embedding is a bag-of-characters projection rather than random noise: the vector arm is
    being exercised for real against a real HNSW index, so two similar strings have to land near
    each other or the test would only be proving that pgvector returns *something*.
    """

    provider = "stub"

    def __init__(
        self,
        *,
        answer: object = None,
        verdicts: list[dict] | None = None,
        fail_generation: bool = False,
        fail_verification: bool = False,
    ) -> None:
        self.model = "stub-model"
        self._answer = answer
        self._verdicts = list(verdicts or [])
        self._fail_generation = fail_generation
        self._fail_verification = fail_verification
        self.temperatures: list[float | None] = []

    async def complete(self, prompt, *, system=None, temperature=None) -> Completion:
        self.temperatures.append(temperature)
        verifying = bool(system and "check whether" in system.lower())
        if verifying and self._fail_verification:
            raise TimeoutError("verifier did not answer in time")
        if not verifying and self._fail_generation:
            raise TimeoutError("model did not answer in time")
        if verifying:
            reply: object = self._verdicts.pop(0) if self._verdicts else {"verdict": "supported"}
        else:
            reply = self._answer if self._answer is not None else {"answer": "", "claims": []}
        body = reply if isinstance(reply, str) else json.dumps(reply, ensure_ascii=False)
        return Completion(text=body, provider=self.provider, model=self.model)

    async def embed(self, text: str) -> list[float]:
        vector = [0.0] * EMBEDDING_DIM
        for token in (text or "").split():
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            vector[int.from_bytes(digest[:4], "big") % EMBEDDING_DIM] += 1.0
        if not any(vector):
            vector[0] = 1.0
        return vector


# --- fixtures ---------------------------------------------------------------------------------


def _purge(session) -> None:
    documents = list(
        session.scalars(select(Document).where(Document.canonical_key.startswith(KEY_PREFIX)))
    )
    ids = [row.id for row in documents]
    if ids:
        versions = list(
            session.scalars(select(DocumentVersion.id).where(DocumentVersion.document_id.in_(ids)))
        )
        if versions:
            answers = select(AnswerCitation.answer_id).where(
                AnswerCitation.document_version_id.in_(versions)
            )
            queries = select(Answer.query_id).where(Answer.id.in_(answers))
            session.execute(
                delete(VerificationResult).where(VerificationResult.answer_id.in_(answers))
            )
            session.execute(
                delete(AnswerCitation).where(AnswerCitation.document_version_id.in_(versions))
            )
            session.execute(delete(Answer).where(Answer.query_id.in_(queries)))
            session.execute(delete(Query).where(Query.id.in_(queries)))
            session.execute(
                delete(ClauseEmbedding).where(ClauseEmbedding.document_version_id.in_(versions))
            )
            session.execute(delete(ClauseDiff).where(ClauseDiff.to_version_id.in_(versions)))
            session.execute(delete(ClauseDiff).where(ClauseDiff.from_version_id.in_(versions)))
            session.execute(delete(Clause).where(Clause.document_version_id.in_(versions)))
        session.execute(delete(DocumentCell).where(DocumentCell.document_id.in_(ids)))
        session.execute(delete(DocumentVersion).where(DocumentVersion.document_id.in_(ids)))
        session.execute(delete(Document).where(Document.id.in_(ids)))
    # Queries a test asked that never produced a citation (the "no retrieval" case) are found by
    # their marker text instead.
    stray = list(session.scalars(select(Query.id).where(Query.text.startswith(KEY_PREFIX))))
    if stray:
        answers = list(session.scalars(select(Answer.id).where(Answer.query_id.in_(stray))))
        if answers:
            session.execute(
                delete(VerificationResult).where(VerificationResult.answer_id.in_(answers))
            )
            session.execute(delete(AnswerCitation).where(AnswerCitation.answer_id.in_(answers)))
            session.execute(delete(Answer).where(Answer.id.in_(answers)))
        session.execute(delete(Query).where(Query.id.in_(stray)))
    session.commit()


@pytest.fixture
def session():
    with sync_session() as db:
        _purge(db)
        yield db
        _purge(db)


@pytest.fixture
def cells(session) -> dict[str, uuid.UUID]:
    wanted = ["mfds_cosmetic", "mfds_samd", "fda_cosmetic", "fda_samd"]
    rows = session.scalars(select(Cell).where(Cell.slug.in_(wanted))).all()
    assert len(rows) == len(wanted), "migration 0001 seeds the 8 cells"
    return {cell.slug: cell.id for cell in rows}


def _document(
    session,
    *,
    key: str,
    title: str,
    cell_id: uuid.UUID | None = None,
    cell_ids: list[uuid.UUID] | None = None,
    doc_type: DocType = DocType.LAW,
) -> Document:
    """One Document, claimed by one cell or by several — ``document_cells`` is M:N (ADR-0002)."""
    claims = cell_ids if cell_ids is not None else [cell_id]
    document = Document(
        canonical_key=f"{KEY_PREFIX}:{key}",
        title=title,
        doc_type=doc_type,
    )
    session.add(document)
    session.flush()
    for claim in claims:
        session.add(DocumentCell(document_id=document.id, cell_id=claim))
    return document


def _version(session, document: Document, *, effective: date, label: str = "v1") -> DocumentVersion:
    version = DocumentVersion(
        document_id=document.id,
        version_group_id=uuid.uuid4(),
        version_label=label,
        language="ko",
        content_hash=uuid.uuid4().hex,
        raw_object_key=f"{KEY_PREFIX}/{label}",
        raw_bytes=1,
        retrieved_at=datetime.now(UTC),
        effective_date=effective,
        parser_version="1.1.0",
    )
    session.add(version)
    session.flush()
    return version


def _clause(
    session,
    version: DocumentVersion,
    *,
    path: str,
    text: str,
    ordinal: int,
    heading: str | None = None,
    kind: ClauseKind = ClauseKind.PROSE,
    parent: Clause | None = None,
    row_columns: dict | list | None = None,
    effective: date | None = None,
) -> Clause:
    clause = Clause(
        document_version_id=version.id,
        clause_path=path,
        path_segments=path.split("/"),
        level=len(path.split("/")),
        ordinal=ordinal,
        kind=kind,
        heading=heading,
        text=text,
        row_columns=row_columns,
        parent_clause_id=parent.id if parent else None,
        effective_date=effective,
        content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
    )
    session.add(clause)
    session.flush()
    return clause


@pytest.fixture
def corpus(session, cells):
    """One law with four articles, an annex table, and a not-yet-effective article."""
    document = _document(
        session, key="law", title="테스트 화장품법", cell_id=cells["mfds_cosmetic"]
    )
    version = _version(session, document, effective=date(2026, 4, 2))

    article = _clause(
        session,
        version,
        path="제5조",
        heading="기록의 보관",
        text="제5조(기록의 보관) 제조업자는 기록을 3년간 보관하여야 한다.",
        ordinal=1,
    )
    _clause(
        session,
        version,
        path="제5조/제1항",
        text="① 제조업자는 제조기록을 3년간 보관하여야 한다.",
        ordinal=2,
        parent=article,
    )
    _clause(
        session,
        version,
        path="제6조",
        heading="표시 의무",
        text="제6조(표시 의무) 화장품의 용기에는 성분을 표시하여야 한다.",
        ordinal=3,
    )
    table = _clause(
        session,
        version,
        path="별표1/표1",
        heading="사용할 수 없는 원료",
        text="",
        ordinal=4,
        kind=ClauseKind.TABLE,
        row_columns=["원료명", "CAS No."],
    )
    _clause(
        session,
        version,
        path="별표1/표1/행1",
        text="갈라민트리에치오다이드 65-29-2",
        ordinal=5,
        kind=ClauseKind.TABLE_ROW,
        parent=table,
        row_columns={"원료명": "갈라민트리에치오다이드", "CAS No.": "65-29-2"},
    )
    _clause(
        session,
        version,
        path="별표1/문단1",
        text="이 표에 열거된 원료는 화장품에 사용할 수 없는 원료이다.",
        ordinal=6,
    )
    session.commit()
    return document, version


@pytest.fixture
def straddling(session, cells):
    """One version whose 조문시행일자 differ — in force beside amended-but-not-yet-effective."""
    document = _document(
        session, key="straddle", title="테스트 시행일법", cell_id=cells["mfds_cosmetic"]
    )
    version = _version(session, document, effective=date(2026, 4, 2), label="s1")
    _clause(
        session,
        version,
        path="제1조",
        heading="신고",
        text="제1조(신고) 책임판매업자는 신고하여야 한다.",
        ordinal=1,
        effective=TODAY - timedelta(days=30),
    )
    _clause(
        session,
        version,
        path="제2조",
        heading="신고 기한",
        text="제2조(신고 기한) 신고는 30일 이내에 하여야 한다.",
        ordinal=2,
        effective=TODAY + timedelta(days=90),
    )
    session.commit()
    return document, version


def _answer_json(text: str, claims: list[tuple[str, int, str | None]]) -> dict:
    return {
        "answer": text,
        "claims": [
            {
                "text": claim,
                "cites": [
                    {"passage": passage, "clause_path": path} if path else {"passage": passage}
                ],
            }
            for claim, passage, path in claims
        ],
    }


def _scope(session, cells, version: DocumentVersion):
    return versions_in_scope(
        session,
        cell_ids=cell_ids_for(session, cell_id=cells["mfds_cosmetic"], cross_cell=False),
        today=TODAY,
        version_ids=[version.id],
    )


# --- criterion: identifier lookup returns the clause at rank 1 ----------------------------------


def test_identifier_lookup_returns_the_named_clause_at_rank_one(session, cells, corpus) -> None:
    _, version = corpus
    client = StubLLM()
    embed_version(session, version.id, client=client)

    result = retrieve(
        session,
        query="제5조가 무엇을 요구하나요",
        versions=_scope(session, cells, version),
        client=client,
        today=TODAY,
    )

    assert result.hits[0].clause_path == "제5조"


# --- criterion: annex ingredient lookup returns the exact row ------------------------------------


def test_annex_lookup_returns_the_row_not_a_neighbouring_paragraph(session, cells, corpus) -> None:
    _, version = corpus
    client = StubLLM()
    embed_version(session, version.id, client=client)

    result = retrieve(
        session,
        query="갈라민트리에치오다이드는 사용할 수 있나?",
        versions=_scope(session, cells, version),
        client=client,
        today=TODAY,
    )

    assert result.hits[0].clause_path == "별표1/표1/행1"
    assert result.hits[0].kind == ClauseKind.TABLE_ROW.value


def test_cas_number_lookup_finds_the_same_row(session, cells, corpus) -> None:
    """An embedding of ``65-29-2`` is meaningless; the lexical/exact arm is what serves this."""
    _, version = corpus
    client = StubLLM()
    embed_version(session, version.id, client=client)

    result = retrieve(
        session,
        query="CAS 65-29-2 의 사용한도는?",
        versions=_scope(session, cells, version),
        client=client,
        today=TODAY,
    )

    assert result.hits[0].clause_path == "별표1/표1/행1"


# --- criterion: annex rows are not embedded ------------------------------------------------------


def test_annex_rows_never_reach_the_index(session, corpus) -> None:
    """ADR-0006 decision 2, on the real index rather than on the passage builder alone."""
    _, version = corpus
    embed_version(session, version.id, client=StubLLM())

    paths = set(
        session.scalars(
            select(Clause.clause_path)
            .join(ClauseEmbedding, ClauseEmbedding.clause_id == Clause.id)
            .where(ClauseEmbedding.document_version_id == version.id)
        )
    )

    assert "별표1/표1/행1" not in paths
    assert "별표1/표1" in paths


def test_re_embedding_an_unchanged_version_spends_no_inference(session, corpus) -> None:
    """The re-embedding path has to be cheap, or a parser bump becomes a model-budget event."""
    _, version = corpus
    client = StubLLM()
    first = embed_version(session, version.id, client=client)
    second = embed_version(session, version.id, client=client)

    assert first.embedded > 0
    assert second.embedded == 0
    assert second.reused == first.embedded


# --- criterion: no supporting clause → "needs verification" --------------------------------------


def test_a_question_nothing_supports_returns_needs_verification(session, cells, corpus) -> None:
    """Never a hedged prose answer. The stub happily offers one; the pipeline discards it."""
    _, version = corpus
    client = StubLLM(answer={"answer": "아마도 3년일 것입니다.", "claims": []})
    embed_version(session, version.id, client=client)

    outcome = ask(
        session,
        question=f"{KEY_PREFIX} 보관 기간은?",
        cell_id=cells["mfds_cosmetic"],
        version_ids=[version.id],
        client=client,
        today=TODAY,
    )

    assert outcome.status is AnswerStatus.NEEDS_VERIFICATION
    assert outcome.no_answer_reason is NoAnswerReason.NO_CITATION
    assert outcome.text == ""
    assert not outcome.is_final


def test_a_fabricated_citation_is_rejected_before_any_verification(session, cells, corpus) -> None:
    """Decision 4 is mechanical: a path retrieval never returned fails the answer outright."""
    _, version = corpus
    client = StubLLM(answer=_answer_json("3년입니다.", [("3년 보관해야 한다.", 1, "제99조")]))
    embed_version(session, version.id, client=client)

    outcome = ask(
        session,
        question=f"{KEY_PREFIX} 기록 보관 기간은?",
        cell_id=cells["mfds_cosmetic"],
        version_ids=[version.id],
        client=client,
        today=TODAY,
    )

    assert outcome.status is AnswerStatus.NEEDS_VERIFICATION
    assert outcome.no_answer_reason is NoAnswerReason.FABRICATED_CITATION
    assert (
        session.scalar(
            select(VerificationResult).where(VerificationResult.answer_id == outcome.answer_id)
        )
        is None
    )


# --- criterion: a mis-cited answer is failed by the verification pass -----------------------------


def test_a_mis_cited_answer_is_failed_by_the_verification_pass(session, cells, corpus) -> None:
    """The clause exists and was retrieved; it just does not say this. Decision 5, class two."""
    _, version = corpus
    client = StubLLM(
        # 제6조 is the labelling article; the claim is about record retention.
        answer=_answer_json("5년입니다.", [("기록은 5년간 보관하여야 한다.", 1, None)]),
        verdicts=[{"verdict": "unsupported", "reason": "the clause is about labelling"}],
    )
    embed_version(session, version.id, client=client)

    outcome = ask(
        session,
        question=f"{KEY_PREFIX} 기록 보관 기간은?",
        cell_id=cells["mfds_cosmetic"],
        version_ids=[version.id],
        client=client,
        today=TODAY,
    )

    assert outcome.status is AnswerStatus.NEEDS_VERIFICATION
    assert outcome.no_answer_reason is NoAnswerReason.UNSUPPORTED_CLAIM
    stored = session.scalars(
        select(VerificationResult).where(VerificationResult.answer_id == outcome.answer_id)
    ).all()
    assert [row.verdict for row in stored] == [VerificationVerdict.UNSUPPORTED]


# --- criterion: sub-threshold confidence routes to review ----------------------------------------


def test_sub_threshold_confidence_routes_to_review(session, cells, corpus) -> None:
    """A partial verdict is not a rejection, and it is not a final answer either."""
    _, version = corpus
    client = StubLLM(
        answer=_answer_json("3년입니다.", [("기록은 3년간 보관하여야 한다.", 1, None)]),
        verdicts=[{"verdict": "partial", "reason": "the scope limit is not stated"}],
    )
    embed_version(session, version.id, client=client)

    outcome = ask(
        session,
        question=f"{KEY_PREFIX} 기록 보관 기간은?",
        cell_id=cells["mfds_cosmetic"],
        version_ids=[version.id],
        client=client,
        today=TODAY,
    )

    assert outcome.status is AnswerStatus.NEEDS_REVIEW
    assert not outcome.is_final
    assert session.get(Answer, outcome.answer_id).is_final is False


def test_a_supported_answer_is_final_and_carries_its_citations(session, cells, corpus) -> None:
    _, version = corpus
    client = StubLLM(
        answer=_answer_json("3년입니다.", [("기록은 3년간 보관하여야 한다.", 1, "제5조/제1항")]),
        verdicts=[{"verdict": "supported"}],
    )
    embed_version(session, version.id, client=client)

    outcome = ask(
        session,
        question=f"{KEY_PREFIX} 기록 보관 기간은?",
        cell_id=cells["mfds_cosmetic"],
        version_ids=[version.id],
        client=client,
        today=TODAY,
    )

    assert outcome.status is AnswerStatus.ANSWERED
    citations = session.scalars(
        select(AnswerCitation).where(AnswerCitation.answer_id == outcome.answer_id)
    ).all()
    assert [row.clause_path for row in citations] == ["제5조/제1항"]
    assert citations[0].document_version_id == version.id
    assert citations[0].effective_date is not None


# --- criterion: every answers row carries provider/model provenance -------------------------------


def test_every_answer_records_provider_and_model_even_when_refusing(session, cells, corpus) -> None:
    _, version = corpus
    client = StubLLM(answer={"answer": "", "claims": []})
    embed_version(session, version.id, client=client)

    outcome = ask(
        session,
        question=f"{KEY_PREFIX} 알 수 없는 질문",
        cell_id=cells["mfds_cosmetic"],
        version_ids=[version.id],
        client=client,
        today=TODAY,
    )

    answer = session.get(Answer, outcome.answer_id)
    assert (answer.llm_provider, answer.llm_model) == ("stub", "stub-model")
    assert answer.prompt_version and answer.retrieval_version


def test_generation_and_verification_run_pinned_to_temperature_zero(session, cells, corpus) -> None:
    """ADR-0017 decision 1, applied to this layer: a delta between runs is a regression."""
    _, version = corpus
    client = StubLLM(
        answer=_answer_json("3년입니다.", [("기록은 3년간 보관하여야 한다.", 1, None)]),
        verdicts=[{"verdict": "supported"}],
    )
    embed_version(session, version.id, client=client)

    ask(
        session,
        question=f"{KEY_PREFIX} 기록 보관 기간은?",
        cell_id=cells["mfds_cosmetic"],
        version_ids=[version.id],
        client=client,
        today=TODAY,
    )

    assert client.temperatures and set(client.temperatures) == {0.0}


# --- criterion: effective-date straddling is called out ------------------------------------------


def test_straddling_clauses_are_called_out_in_the_answer(session, cells, straddling) -> None:
    """The API returns 조문시행일자 per clause, so this is routine rather than exotic."""
    _, version = straddling
    client = StubLLM(
        answer=_answer_json("30일 이내입니다.", [("신고는 30일 이내에 하여야 한다.", 1, None)]),
        verdicts=[{"verdict": "supported"}, {"verdict": "supported"}],
    )
    embed_version(session, version.id, client=client)

    outcome = ask(
        session,
        question=f"{KEY_PREFIX} 신고 기한은?",
        cell_id=cells["mfds_cosmetic"],
        version_ids=[version.id],
        client=client,
        today=TODAY,
    )

    assert outcome.straddles_effective_date
    assert "시행일이 일치하지 않습니다" in outcome.text
    assert session.get(Answer, outcome.answer_id).straddles_effective_date


# --- criterion: an amended clause supersedes the citation, never rewrites it ----------------------


def test_an_amendment_flags_the_citation_and_leaves_it_resolvable(session, cells, corpus) -> None:
    """Citation immutability: flagged superseded, not repointed at the new version."""
    document, version = corpus
    client = StubLLM(
        answer=_answer_json("3년입니다.", [("기록은 3년간 보관하여야 한다.", 1, "제5조/제1항")]),
        verdicts=[{"verdict": "supported"}],
    )
    embed_version(session, version.id, client=client)
    outcome = ask(
        session,
        question=f"{KEY_PREFIX} 기록 보관 기간은?",
        cell_id=cells["mfds_cosmetic"],
        version_ids=[version.id],
        client=client,
        today=TODAY,
    )
    original_text = session.scalar(
        select(Clause.text).where(
            Clause.document_version_id == version.id, Clause.clause_path == "제5조/제1항"
        )
    )

    amended = _version(session, document, effective=date(2026, 10, 1), label="v2")
    _clause(
        session,
        amended,
        path="제5조/제1항",
        text="① 제조업자는 제조기록을 5년간 보관하여야 한다.",
        ordinal=1,
    )
    session.add(
        ClauseDiff(
            from_version_id=version.id,
            to_version_id=amended.id,
            clause_path="제5조/제1항",
            change_kind=ChangeKind.MODIFIED,
        )
    )
    session.commit()

    result = supersede_for_version(session, amended.id)
    session.commit()

    citation = session.scalar(
        select(AnswerCitation).where(AnswerCitation.answer_id == outcome.answer_id)
    )
    assert result.citations_superseded == 1
    assert citation.superseded_at is not None
    assert citation.superseded_by_diff_id is not None
    # Not rewritten: still points at the version it was written from, and that text is unchanged.
    assert citation.document_version_id == version.id
    assert citation.clause_path == "제5조/제1항"
    assert (
        session.scalar(
            select(Clause.text).where(
                Clause.document_version_id == version.id, Clause.clause_path == "제5조/제1항"
            )
        )
        == original_text
    )


def test_the_answer_itself_joins_the_superseded_queue(session, cells, corpus) -> None:
    """Surfaced as a product feature: an answer over moved evidence must stop reading as current."""
    document, version = corpus
    client = StubLLM(
        answer=_answer_json("3년입니다.", [("기록은 3년간 보관하여야 한다.", 1, "제5조/제1항")]),
        verdicts=[{"verdict": "supported"}],
    )
    embed_version(session, version.id, client=client)
    outcome = ask(
        session,
        question=f"{KEY_PREFIX} 기록 보관 기간은?",
        cell_id=cells["mfds_cosmetic"],
        version_ids=[version.id],
        client=client,
        today=TODAY,
    )

    amended = _version(session, document, effective=date(2026, 10, 1), label="v3")
    session.add(
        ClauseDiff(
            from_version_id=version.id,
            to_version_id=amended.id,
            clause_path="제5조/제1항",
            change_kind=ChangeKind.MODIFIED,
        )
    )
    session.commit()
    supersede_for_version(session, amended.id)
    session.commit()

    assert session.get(Answer, outcome.answer_id).superseded_at is not None


def test_a_newly_added_clause_supersedes_nothing(session, cells, corpus) -> None:
    """A clause that did not exist before cannot have been cited."""
    document, version = corpus
    amended = _version(session, document, effective=date(2026, 10, 1), label="v4")
    session.add(
        ClauseDiff(
            from_version_id=version.id,
            to_version_id=amended.id,
            clause_path="제7조",
            change_kind=ChangeKind.ADDED,
        )
    )
    session.commit()

    assert supersede_for_version(session, amended.id).citations_superseded == 0


# --- criterion: retrieval is cell-scoped ----------------------------------------------------------


def test_retrieval_does_not_cross_the_cell_boundary(session, cells, corpus) -> None:
    """ADR-0006 decision 9. A cosmetic question answered from device regulation is the worst
    failure this product can produce, so cross-cell is opt-in and this proves the default."""
    _, version = corpus
    client = StubLLM()
    embed_version(session, version.id, client=client)

    scoped = versions_in_scope(
        session,
        cell_ids=cell_ids_for(session, cell_id=cells["mfds_samd"], cross_cell=False),
        today=TODAY,
    )

    assert version.id not in {row.version_id for row in scoped}


def test_cross_cell_is_an_explicit_mode_that_widens_the_scope(session, cells, corpus) -> None:
    _, version = corpus

    scoped = versions_in_scope(
        session,
        cell_ids=cell_ids_for(session, cell_id=cells["mfds_samd"], cross_cell=True),
        today=TODAY,
    )

    assert version.id in {row.version_id for row in scoped}


# --- criterion: the "needs verification" rate is reportable per domain ----------------------------


def test_the_needs_verification_rate_is_reportable_per_domain(session, cells, corpus) -> None:
    """A system that refuses everything passes both gates cleanly, so the gates are not
    self-guarding. This is the number that makes that visible (decision 7)."""
    from app.api.v1.queries import _DOMAIN_COUNTS, _counts_from, _rate_block

    _, version = corpus
    embed_version(session, version.id, client=StubLLM())
    refusing = StubLLM(answer={"answer": "", "claims": []})
    answering = StubLLM(
        answer=_answer_json("3년입니다.", [("기록은 3년간 보관하여야 한다.", 1, "제5조/제1항")]),
        verdicts=[{"verdict": "supported"}],
    )
    for client in (refusing, answering):
        ask(
            session,
            question=f"{KEY_PREFIX} 기록 보관 기간은?",
            cell_id=cells["mfds_cosmetic"],
            version_ids=[version.id],
            client=client,
            today=TODAY,
        )

    rows = list(session.execute(_DOMAIN_COUNTS))
    block = _rate_block(_counts_from(rows, "cosmetic"))

    assert block["total"] >= 2
    assert block["needs_verification"] >= 1
    assert block["answered"] >= 1
    assert 0.0 < block["needs_verification_rate"] < 1.0


def test_a_model_that_never_answers_is_recorded_not_lost(session, cells, corpus) -> None:
    """A question that was asked has to end in a stored outcome.

    Found by running the real thing: a generation call that timed out raised out of the task and
    left the query row with **no answer at all** — the asker watches a spinner, and the monitored
    rate silently excludes every failure, which is the one direction that makes it look healthy.
    """
    _, version = corpus
    embed_version(session, version.id, client=StubLLM())
    client = StubLLM(fail_generation=True)

    outcome = ask(
        session,
        question=f"{KEY_PREFIX} 모델이 응답하지 않는 경우",
        cell_id=cells["mfds_cosmetic"],
        version_ids=[version.id],
        client=client,
        today=TODAY,
    )

    assert outcome.status is AnswerStatus.NEEDS_VERIFICATION
    assert outcome.no_answer_reason is NoAnswerReason.MODEL_UNAVAILABLE
    assert session.get(Answer, outcome.answer_id) is not None


def test_a_verifier_that_never_answers_does_not_pass_the_answer_through(
    session, cells, corpus
) -> None:
    """Unverified is unsupported: claims that were never checked must not read as final."""
    _, version = corpus
    embed_version(session, version.id, client=StubLLM())
    client = StubLLM(
        answer=_answer_json("3년입니다.", [("기록은 3년간 보관하여야 한다.", 1, "제5조/제1항")]),
        fail_verification=True,
    )

    outcome = ask(
        session,
        question=f"{KEY_PREFIX} 검증이 실패하는 경우",
        cell_id=cells["mfds_cosmetic"],
        version_ids=[version.id],
        client=client,
        today=TODAY,
    )

    assert outcome.status is AnswerStatus.NEEDS_VERIFICATION
    assert outcome.no_answer_reason is NoAnswerReason.MODEL_UNAVAILABLE
    assert not outcome.is_final


def test_a_refusal_records_a_reason_from_the_closed_inventory(session, cells, corpus) -> None:
    """A rate whose causes cannot be counted tells you it moved without telling you why."""
    _, version = corpus
    client = StubLLM(answer={"answer": "", "claims": []})
    embed_version(session, version.id, client=client)

    outcome = ask(
        session,
        question=f"{KEY_PREFIX} 알 수 없는 질문",
        cell_id=cells["mfds_cosmetic"],
        version_ids=[version.id],
        client=client,
        today=TODAY,
    )

    assert session.get(Answer, outcome.answer_id).no_answer_reason in {
        reason.value for reason in NoAnswerReason
    }


# --- version pinning ------------------------------------------------------------------------------


def test_an_answer_names_the_versions_it_was_drawn_from(session, cells, corpus) -> None:
    """Never "latest" implicitly: a stored answer must be re-checkable against its evidence."""
    _, version = corpus
    client = StubLLM(
        answer=_answer_json("3년입니다.", [("기록은 3년간 보관하여야 한다.", 1, None)]),
        verdicts=[{"verdict": "supported"}],
    )
    embed_version(session, version.id, client=client)

    outcome = ask(
        session,
        question=f"{KEY_PREFIX} 기록 보관 기간은?",
        cell_id=cells["mfds_cosmetic"],
        version_ids=[version.id],
        client=client,
        today=TODAY,
    )

    answer = session.get(Answer, outcome.answer_id)
    assert answer.document_version_scope == [version.id]
    assert answer.effective_date_scope is not None


def test_scoping_picks_the_version_in_force_not_the_newest(session, cells) -> None:
    """A pending version is published but not yet law; answering from it would be wrong today."""
    document = _document(
        session, key="inforce", title="테스트 시행중법", cell_id=cells["mfds_cosmetic"]
    )
    in_force = _version(session, document, effective=TODAY - timedelta(days=10), label="now")
    _version(session, document, effective=TODAY + timedelta(days=90), label="pending")
    session.commit()

    scoped = versions_in_scope(
        session,
        cell_ids=cell_ids_for(session, cell_id=cells["mfds_cosmetic"], cross_cell=False),
        today=TODAY,
    )

    picked = [row for row in scoped if row.document_id == document.id]
    assert [row.version_id for row in picked] == [in_force.id]


# --- criterion: cell scope holds for a document two cells share ------------------------------


def test_a_shared_act_is_in_scope_for_both_claiming_cells_and_a_single_cell_one_is_not(
    session, cells
) -> None:
    """*An `fda_cosmetic` question must not be answered from `fda_samd` clauses of the same act.*

    **That criterion does not hold as written, and this is the coherent form of it.** The FD&C Act
    is *one* Document claimed by both FDA cells, so its clauses belong to both — there is no
    `fda_samd` subset of the same act to refuse. Refusing it would be the bug: the Act is the
    statute the cosmetic cell is governed by.

    What must be refused is a document the other cell claims *alone*. 21 CFR Part 892 (Radiology
    Devices) is `fda_samd` only, and a cosmetic question reaching it is the confident wrong answer
    ADR-0006 decision 9 exists to prevent. Both halves are asserted here, because either one alone
    is satisfiable by a scope that is simply wrong in the other direction.

    Scope is enforced in `versions_in_scope`, so that is where this is measured — no model involved.
    """
    today = date(2026, 8, 25)

    shared = _document(
        session,
        key="fdc_act",
        title="21 U.S.C. chapter 9 — Federal Food, Drug, and Cosmetic Act",
        cell_ids=[cells["fda_samd"], cells["fda_cosmetic"]],
        doc_type=DocType.CODIFIED_STATUTE,
    )
    _version(session, shared, effective=date(2024, 12, 31), label="USCODE-2024-title21")

    samd_only = _document(
        session,
        key="cfr_892",
        title="21 CFR Part 892 — Radiology Devices",
        cell_id=cells["fda_samd"],
        doc_type=DocType.REGULATION,
    )
    _version(session, samd_only, effective=date(2026, 2, 4), label="2026-02-04")
    session.commit()

    def in_scope(slug: str) -> set[uuid.UUID]:
        return {
            ref.document_id
            for ref in versions_in_scope(
                session,
                cell_ids=cell_ids_for(session, cell_id=cells[slug], cross_cell=False),
                today=today,
            )
        }

    cosmetic, samd = in_scope("fda_cosmetic"), in_scope("fda_samd")

    assert shared.id in cosmetic, "the cosmetic cell is governed by the FD&C Act"
    assert shared.id in samd, "and so is the device cell — one Document, two claims"
    assert samd_only.id in samd
    assert samd_only.id not in cosmetic, "a cosmetic question reached device-only regulation"
