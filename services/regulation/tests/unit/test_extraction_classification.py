"""How an obligation-bearing clause that yields no IR gets classified.

This is the narrow seam where a *prompt regression* can hide inside a *legitimate verdict*. A clause
carrying an inventory modal that produces no storable IR is either:

- ``no_obligation`` — the agent read it and found no duty. Common and correct.
- ``unparseable`` — the agent answered nothing usable, or everything it proposed was rejected.

Both are ``excluded`` and both are on the record, so coverage looks identical either way. Only the
*reason* distinguishes them, which makes the reason the whole signal: a run whose ``unparseable``
count jumps is a prompt or model regression, and it is invisible if the two collapse into one value.
"""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from app.extraction.agent import AgentResult, Proposal
from app.extraction.extract import (
    ExtractionResult,
    _process,
    _RoleTrail,
    describe_exception,
)
from app.extraction.rules import rule_set_for
from regops_shared.constants import ClassificationKind, Domain, ExclusionReason

RULES = rule_set_for(Domain.SAMD, "ko")


class _Recorder:
    """Stands in for the session and for :func:`_classify`'s persistence.

    Only two things are under test — which reason each clause lands on, and that every clause lands
    on exactly one — so a recorder beats a database here.
    """

    def __init__(self) -> None:
        self.classified: list[tuple[ClassificationKind, ExclusionReason | None]] = []

    def scalar(self, _stmt):
        return None

    def add(self, _row):
        pass

    def flush(self):
        pass


@pytest.fixture
def captured(monkeypatch) -> list:
    rows: list = []

    def _fake_classify(_session, clause, *, run, rules, verdict, result):
        rows.append((clause.clause_path, verdict.kind, verdict.reason))

    monkeypatch.setattr("app.extraction.extract._classify", _fake_classify)
    return rows


def _clause(text: str = "제조업자는 기록을 보관하여야 한다."):
    from regops_shared.constants import ClauseKind

    return SimpleNamespace(
        id="c1",
        clause_path="제5조",
        path_segments=["제5조"],
        heading="기록의 보관",
        text=text,
        kind=ClauseKind.PROSE,
        effective_date=None,
    )


def _run_process(monkeypatch, captured, agent: AgentResult, *, written: int, rejects: int = 0):
    monkeypatch.setattr("app.extraction.extract.extract_clause", lambda *a, **k: agent)

    def _fake_persist(_session, _agent, *, run, rules, clause, document, version, result):
        result.rejected_uncited += rejects
        return written

    monkeypatch.setattr("app.extraction.extract.persist_proposals", _fake_persist)

    result = ExtractionResult(document_version_id="v1", domain_profile=Domain.SAMD)
    result.rejected_uncited = 7  # a run-wide backlog from earlier clauses
    _process(
        _Recorder(),
        _clause(),
        run=SimpleNamespace(id="r1"),
        rules=RULES,
        client=object(),
        document=SimpleNamespace(id="d1"),
        version=SimpleNamespace(id="v1", effective_date=None),
        result=result,
        roles=_RoleTrail(),
    )
    return captured[-1]


def _agent(**overrides) -> AgentResult:
    base = AgentResult(provider="stub", model="stub-model")
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def test_an_earlier_clauses_rejection_does_not_taint_this_one(monkeypatch, captured) -> None:
    """The regression signal is a **delta**, not the run-wide counter.

    Reading ``result.rejected_uncited`` directly would label every later empty clause
    ``unparseable`` once any one clause had a rejection — turning a single bad proposal into a
    run-wide false alarm and burying the real signal under it.
    """
    _, kind, reason = _run_process(monkeypatch, captured, _agent(), written=0, rejects=0)

    assert kind is ClassificationKind.EXCLUDED
    assert reason is ExclusionReason.NO_OBLIGATION


def test_a_rejection_on_this_clause_marks_it_unparseable(monkeypatch, captured) -> None:
    _, _, reason = _run_process(monkeypatch, captured, _agent(), written=0, rejects=1)
    assert reason is ExclusionReason.UNPARSEABLE


def test_nothing_parseable_marks_it_unparseable(monkeypatch, captured) -> None:
    _, _, reason = _run_process(monkeypatch, captured, _agent(unparseable=True), written=0)
    assert reason is ExclusionReason.UNPARSEABLE


def test_everything_discarded_marks_it_unparseable(monkeypatch, captured) -> None:
    """A modal outside the inventory is the agent answering unusably, not the clause being empty."""
    agent = _agent(discarded=["[0] modal outside the inventory: '바람직하다'"])
    _, _, reason = _run_process(monkeypatch, captured, agent, written=0)
    assert reason is ExclusionReason.UNPARSEABLE


def test_a_clause_that_yields_an_ir_is_obligation_bearing(monkeypatch, captured) -> None:
    agent = _agent(
        proposals=[
            Proposal(
                bearer="제조업자",
                modal="하여야 한다",
                statement="기록을 보관",
                condition_text=None,
                taxonomy_code=None,
                cites=("제5조",),
            )
        ]
    )
    _, kind, reason = _run_process(monkeypatch, captured, agent, written=1)

    assert kind is ClassificationKind.OBLIGATION_BEARING
    assert reason is None


# --- a failure that says what failed --------------------------------------------------------------


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (httpx.ReadTimeout(""), "httpx.ReadTimeout"),
        (httpx.ConnectError(""), "httpx.ConnectError"),
        (RuntimeError(""), "RuntimeError"),
        (ValueError("clause 42 has no citation"), "ValueError: clause 42 has no citation"),
    ],
)
def test_a_failure_reason_survives_an_exception_with_no_message(exc, expected) -> None:
    """**The transport errors that actually end a run carry no message.** `run.error` was
    `str(exc)`, which is right for anything raised with a sentence and empty for these: a run over
    the FD&C Act died on `httpx.ReadTimeout` after 291 of 12,179 clauses and recorded its reason as
    `''`. The column exists so a failure is legible without opening a worker log, and it said
    nothing.

    The type leads because for a timeout it *is* the answer; a message follows where there is one.
    """
    assert describe_exception(exc) == expected


def test_a_long_message_is_truncated_to_the_column() -> None:
    assert len(describe_exception(ValueError("x" * 5000))) == 2000
