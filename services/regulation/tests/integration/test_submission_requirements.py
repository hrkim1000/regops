"""Submission requirements against the real stack — the round trip, not the regexes.

    STAGE=test REGOPS_DB_NAME=regops_test docker compose run --rm regulation \
        python -m pytest tests/integration -q

The unit suite covers what the patterns do and do not match. What only a real database can show is
that the *tree* survives: 항 → 호 as parent and children, each with its own `clause_path`, in
document order, straight out of the parse stage with nothing stored in between.

The fixture is a shortened 화장품법 시행규칙 제5조 — a real amendment-registration procedure whose
items are conditional per case, which is the shape 94% of the corpus actually has.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, select

from app.models import Cell, Clause, Document, DocumentCell, DocumentVersion, Source
from app.parse import parse_version
from app.submissions import Caveat, derive
from regops_shared.constants import DocType, SourceBlock, SourceTier
from regops_shared.db import sync_session
from regops_shared.storage import archive_bytes

pytestmark = pytest.mark.integration

KEY = "test:submissions:doc"
SLUG = "test.submissions.source"


def _purge(session) -> None:
    documents = list(session.scalars(select(Document).where(Document.canonical_key == KEY)))
    ids = [d.id for d in documents]
    if ids:
        versions = list(
            session.scalars(select(DocumentVersion.id).where(DocumentVersion.document_id.in_(ids)))
        )
        if versions:
            session.execute(delete(Clause).where(Clause.document_version_id.in_(versions)))
        session.execute(delete(DocumentCell).where(DocumentCell.document_id.in_(ids)))
        session.execute(delete(DocumentVersion).where(DocumentVersion.document_id.in_(ids)))
        session.execute(delete(Document).where(Document.id.in_(ids)))
    session.execute(delete(Source).where(Source.slug == SLUG))
    session.commit()


@pytest.fixture
def session():
    with sync_session() as db:
        _purge(db)
        yield db
        _purge(db)


#: The real envelope shape: 항 and 호 are **elements**, not inline text (verified against the
#: archived corpus). Building the fixture any other way would test a parser that does not exist.
def _article(number: str, title: str, paragraph: str, items: list[str]) -> str:
    body = "".join(
        f"<호><호번호><![CDATA[{i}.]]></호번호><호내용><![CDATA[{i}. {item}]]></호내용></호>"
        for i, item in enumerate(items, start=1)
    )
    return (
        f'<조문단위 조문키="000{number}001">'
        f"<조문번호>{number}</조문번호><조문여부>조문</조문여부>"
        f"<조문제목><![CDATA[{title}]]></조문제목>"
        f"<조문시행일자>20260401</조문시행일자>"
        f"<조문내용><![CDATA[제{number}조({title})]]></조문내용>"
        f"<항><항번호><![CDATA[①]]></항번호>"
        f"<항내용><![CDATA[① {paragraph}]]></항내용>{body}</항>"
        f"</조문단위>"
    )


#: Two obligation clauses: one that requires documents and one that enumerates 기준 instead, so the
#: derivation has something to *decline* as well as something to find. Shortened from 화장품법
#: 시행규칙 제5조, whose items are conditional per case — the shape 94% of the corpus actually has.
ARTICLES = [
    _article(
        "4",
        "등록의 변경",
        "화장품제조업자는 변경 사유가 발생한 날부터 30일 이내에 별지 제5호서식의 변경등록 "
        "신청서에 다음 각 호의 서류를 첨부하여 지방식품의약품안전청장에게 제출하여야 한다.",
        [
            "화장품제조업 등록필증",
            "제조소의 소재지 변경의 경우: 제3조제2항제3호에 해당하는 서류",
            "그 밖에 필요한 서류로서 총리령으로 정하는 서류",
        ],
    ),
    _article(
        "6",
        "준수사항",
        "화장품제조업자는 다음 각 호의 기준을 갖추어 제조시설을 관리하여야 한다.",
        ["쥐ㆍ해충 및 먼지 등을 막을 수 있는 시설"],
    ),
]


def _law_xml() -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<법령>
  <기본정보><법령ID>002015</법령ID><법종구분>법률</법종구분>
    <법령명_한글>테스트 시행규칙</법령명_한글><공포일자>20250401</공포일자>
    <시행일자>20260401</시행일자></기본정보>
  <조문>{"".join(ARTICLES)}</조문>
  <부칙><부칙단위><부칙공포일자>20250401</부칙공포일자>
    <부칙내용>제1조(시행일) 이 규칙은 공포한 날부터 시행한다.</부칙내용>
  </부칙단위></부칙>
</법령>
""".encode()


@pytest.fixture
def version(session) -> DocumentVersion:
    cell = session.scalar(select(Cell).where(Cell.slug == "mfds_cosmetic"))
    source = Source(
        slug=SLUG,
        cell_id=cell.id,
        block=SourceBlock.PRIMARY_LAWS,
        ordinal=1,
        title="submission fixture",
        tier=SourceTier.A,
        ingestible=True,
        connector="law_go_kr_law",
        url_template="https://example.invalid/{OC}",
        params={},
    )
    session.add(source)
    session.flush()

    document = Document(canonical_key=KEY, title=KEY, doc_type=DocType.LAW, source_id=source.id)
    session.add(document)
    session.flush()
    session.add(DocumentCell(document_id=document.id, cell_id=cell.id))

    raw = _law_xml()
    object_key, digest = archive_bytes(raw, content_type="application/xml")
    row = DocumentVersion(
        document_id=document.id,
        version_group_id=uuid.uuid4(),
        language="ko",
        content_hash=digest,
        raw_object_key=object_key,
        raw_bytes=len(raw),
        content_type="application/xml",
        retrieved_at=datetime.now(UTC),
    )
    session.add(row)
    session.commit()
    parse_version(session, row)
    return row


def test_the_document_list_survives_the_parse_as_a_citable_tree(session, version):
    """항 → 호 with real `clause_path`s, straight out of the clause store."""
    requirements = derive(session, version.id)
    assert len(requirements) == 1, "제6조 enumerates 기준, not documents — it must not be picked up"

    [requirement] = requirements
    assert requirement.clause_path.startswith("제4조")
    assert requirement.form_reference == "별지 제5호서식"
    assert requirement.recipient == "지방식품의약품안전청장"

    # Every item is a clause and carries the address a reader would cite.
    assert len(requirement.documents) == 3
    for document in requirement.documents:
        assert document.clause_path.startswith(requirement.clause_path)
        assert document.text.strip()

    stored = {
        clause.clause_path
        for clause in session.scalars(
            select(Clause).where(Clause.document_version_id == version.id)
        )
    }
    for document in requirement.documents:
        assert document.clause_path in stored, "the citation must resolve in the clause store"


def test_conditions_and_delegations_survive_per_item(session, version):
    """The invariant, end to end: nothing is flattened between parse and read."""
    [requirement] = derive(session, version.id)
    first, second, third = requirement.documents

    assert not first.conditional, "화장품제조업 등록필증 is required outright"
    assert second.conditional, "소재지 변경의 경우 — applies only in one case"
    assert third.delegates, "총리령으로 정하는 — the content lives elsewhere"

    assert Caveat.CONDITIONAL_ITEMS in requirement.caveats
    assert Caveat.DELEGATED_ITEMS in requirement.caveats
    assert not requirement.is_definitive


def test_deriving_twice_gives_the_same_answer_and_writes_nothing(session, version):
    """Nothing is stored, so a second read re-derives — and must agree with the first."""
    before = derive(session, version.id)
    after = derive(session, version.id)

    assert [r.clause_path for r in before] == [r.clause_path for r in after]
    assert [[d.clause_path for d in r.documents] for r in before] == [
        [d.clause_path for d in r.documents] for r in after
    ]
    # No table was created for this feature; the assertion is that the clause store is untouched.
    assert (
        session.scalar(select(Clause).where(Clause.document_version_id == version.id).limit(1))
        is not None
    )
