"""Closing out runs the previous worker did not live to finish.

`extract_version` marks a dying run `failed` from its own `except` block, and that handler does not
run when the worker is killed. A restart therefore left one run reading `running` forever — the one
state its comment exists to prevent — and the only way back was hand-written SQL.

What is worth testing is the **boundary**, not the sweep. Failing every `running` row would be
trivially correct on an idle worker and wrong on a busy one: with `task_acks_late` a redelivered
task can be picked up before `worker_ready` is handled, and the sweep would then fail a run this
worker had just begun.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest

from app.celery_app import _BOOTED_AT, _fail_orphaned_runs
from regops_shared.constants import Domain, ExtractionRunStatus
from regops_shared.models import ExtractionRun


def _run(started_at: datetime, **overrides) -> ExtractionRun:
    run = ExtractionRun(
        document_version_id=uuid.uuid4(),
        domain_profile=Domain.SAMD,
        status=ExtractionRunStatus.RUNNING,
        clauses_seen=50,
        irs_written=8,
        started_at=started_at,
    )
    for key, value in overrides.items():
        setattr(run, key, value)
    return run


class _Session:
    """Records what the sweep selected and whether it committed."""

    def __init__(self, rows: list[ExtractionRun]) -> None:
        self._rows = rows
        self.committed = False
        self.criteria: list[object] = []

    def scalars(self, statement):
        # The **WHERE clause only**. `str(statement)` renders the column list too, where
        # `started_at` appears whatever the filter says — an earlier version of this test asserted
        # against the whole statement and passed with the predicate deleted.
        self.criteria.append(str(statement.whereclause))
        return _Result(self._rows)

    def commit(self) -> None:
        self.committed = True

    def __enter__(self):
        return self

    def __exit__(self, *_exc) -> None:
        return None


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


@pytest.fixture
def swept(monkeypatch):
    """Run the sweep against a fake session and hand back what it saw."""

    def _run_sweep(rows: list[ExtractionRun]) -> _Session:
        session = _Session(rows)
        monkeypatch.setattr("regops_shared.db.sync_session", lambda: session)
        _fail_orphaned_runs()
        return session

    return _run_sweep


def test_a_run_from_before_this_boot_is_closed_with_a_reason(swept) -> None:
    """The case that forced this: a worker restart mid-extraction. The row said `running` and the
    process that owned it was gone."""
    orphan = _run(_BOOTED_AT - timedelta(minutes=9))
    session = swept([orphan])

    assert orphan.status is ExtractionRunStatus.FAILED
    assert orphan.completed_at is not None
    assert "orphaned" in (orphan.error or "")
    # The reason carries how far it got, because "re-run or not" is the reader's next question.
    assert "50 clauses" in orphan.error
    assert "8 draft IRs" in orphan.error
    assert session.committed


def test_the_sweep_asks_only_for_runs_older_than_this_boot(swept) -> None:
    """**The boundary, asserted on the query rather than on a fake's obedience.**

    `worker_ready` firing is not proof that nothing of this worker's is in flight: `task_acks_late`
    can hand a redelivered task over before the signal is handled, and a sweep filtering on status
    alone would fail a run this worker had just begun.

    The fake session returns whatever it is given, so asserting on its rows would prove nothing —
    the predicate has to be read off the statement the sweep actually built.
    """
    session = swept([])

    (where,) = session.criteria
    assert "started_at" in where, (
        "the boot-time predicate is gone; the sweep can now fail runs this worker started"
    )
    assert "status" in where
    assert session.committed


def test_a_sweep_failure_does_not_stop_the_worker_booting(monkeypatch) -> None:
    """A worker that cannot tidy up is still a worker that can work."""

    def _boom():
        raise RuntimeError("database is not up yet")

    monkeypatch.setattr("regops_shared.db.sync_session", _boom)
    _fail_orphaned_runs()  # must not raise
