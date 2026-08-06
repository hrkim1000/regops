"""An annex the authority lists but returns no text for must not vanish silently.

The gap this covers is a *hole between two stages*, which is why it needs its own test: an empty
``별표내용`` yields no artefact, so no Document is created, so the parse stage — which is where
``EMPTY_ANNEX_BODY`` is raised — never sees it. Both stages behave correctly and the annex is still
gone. Measured on the live corpus: 9 such annexes, 5 of them in 의약품등의 타르색소 지정과 기준 및
시험방법, whose 별표 *are* the colorant list.
"""

from __future__ import annotations

from app.connectors.base import SourceSpec
from app.connectors.law_go_kr import AdmRuleConnector
from regops_shared.constants import SourceTier

SPEC = SourceSpec(
    slug="test.empty_annex",
    title="테스트 고시",
    tier=SourceTier.A,
    ingestible=True,
    url_template="https://example.invalid/{OC}",
    params={},
)

BODY = """<?xml version="1.0" encoding="UTF-8"?>
<AdmRulService>
  <행정규칙기본정보>
    <행정규칙일련번호>33326</행정규칙일련번호>
    <행정규칙명>의약품등의 타르색소 지정과 기준 및 시험방법</행정규칙명>
    <시행일자>20160823</시행일자>
  </행정규칙기본정보>
  <조문내용>제1조(목적) 목적.</조문내용>
  <별표>
    <별표단위>
      <별표번호>0001</별표번호><별표가지번호>00</별표가지번호>
      <별표구분>별표</별표구분><별표제목>타르색소</별표제목>
      <별표서식파일링크>/LSW/flDownload.do?flSeq=1</별표서식파일링크>
      <별표내용></별표내용>
    </별표단위>
    <별표단위>
      <별표번호>0002</별표번호><별표가지번호>00</별표가지번호>
      <별표구분>별표</별표구분><별표제목>있는 것</별표제목>
      <별표내용>제1조 실제 내용이 있습니다.</별표내용>
    </별표단위>
    <별표단위>
      <별표번호>0003</별표번호><별표가지번호>00</별표가지번호>
      <별표구분>서식</별표구분><별표제목>빈 서식</별표제목>
      <별표내용>   </별표내용>
    </별표단위>
  </별표>
</AdmRulService>
"""


def test_an_empty_annex_produces_no_artefact() -> None:
    """The existing behaviour, pinned: it is skipped rather than archived as an empty document."""
    artifacts = AdmRuleConnector().parse(BODY.encode(), spec=SPEC)
    keys = {a.ref.canonical_key for a in artifacts}

    assert any(k.endswith("#별표2") for k in keys)
    assert not any(k.endswith("#별표1") for k in keys)
    assert not any(k.endswith("#서식3") for k in keys)


def test_the_skipped_annexes_are_reported_so_they_do_not_vanish() -> None:
    """Whitespace counts as empty — ``   `` is not annex text."""
    assert AdmRuleConnector().empty_annexes(BODY.encode()) == ("별표1", "서식3")


def test_a_response_with_no_empty_annex_reports_nothing() -> None:
    """No alert where there is nothing wrong; the operator channel stays quiet."""
    body = BODY.replace("<별표내용></별표내용>", "<별표내용>제1조 내용.</별표내용>").replace(
        "<별표내용>   </별표내용>", "<별표내용>제1조 내용.</별표내용>"
    )
    assert AdmRuleConnector().empty_annexes(body.encode()) == ()


def test_a_malformed_body_reports_nothing_rather_than_raising() -> None:
    """The caller has already failed closed on a bad envelope; this must not raise a second time
    and mask the real signal."""
    assert AdmRuleConnector().empty_annexes(b"<not-xml") == ()
