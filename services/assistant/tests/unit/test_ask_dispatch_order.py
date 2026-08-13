"""The question row must be committed before its task is dispatched.

Found by running the phase 1.6 harness: dispatching first is a race the worker wins often enough to
matter. It picked the task up, found no row, logged ``answer.unknown_query`` and returned
*success* — leaving a question that would never be answered, with no retry and no signal. The
asker watched a spinner to the poll ceiling.

The reverse failure is strictly better and is why this ordering is the invariant rather than a
preference: a crash between the commit and the dispatch leaves a committed question with no worker,
which is visible in the UI with an elapsed clock and can be dispatched again, because the row is
there to dispatch for. An orphaned task is neither.
"""

from __future__ import annotations

import uuid

import pytest

from app.api.v1.queries import AskRequest, ask_question
from regops_shared.auth import Principal
from regops_shared.constants import Role


class RecordingSession:
    """Records the order of the two operations whose order is the invariant."""

    def __init__(self) -> None:
        self.events: list[str] = []
        self.added: list[object] = []

    def add(self, instance: object) -> None:
        self.added.append(instance)
        self.events.append("add")

    async def flush(self) -> None:
        self.events.append("flush")
        self._assign_ids()

    async def commit(self) -> None:
        self.events.append("commit")
        self._assign_ids()

    def _assign_ids(self) -> None:
        """Mirror the real flush: the Python-side ``default=uuid.uuid4`` fires there, not on add.

        Without this the fake would hand the dispatcher ``None`` where the real session hands it a
        uuid — and the test would pass on an endpoint that never committed at all, because a
        never-flushed row also has no id.
        """
        for instance in self.added:
            if getattr(instance, "id", None) is None:
                instance.id = uuid.uuid4()


class RecordingCelery:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def send_task(self, name: str, *, args: list[str], queue: str) -> object:
        self.events.append("send_task")
        assert name == "assistant.answer_query"
        assert queue == "assistant"
        assert uuid.UUID(args[0])  # the id the worker will look the row up by
        return type("Task", (), {"id": "task-1"})()


@pytest.fixture
def principal() -> Principal:
    return Principal(id=uuid.uuid4(), email="ra@example.com", role=Role.RA)


async def test_the_row_is_committed_before_the_task_is_dispatched(monkeypatch, principal):
    import app.celery_app as celery_module

    session = RecordingSession()
    monkeypatch.setattr(celery_module, "celery_app", RecordingCelery(session.events))

    body = AskRequest(text="화장품법 제5조는?", cell_id=uuid.uuid4())
    response = await ask_question(body, session, principal)  # type: ignore[arg-type]

    assert "commit" in session.events, "the question row was never committed"
    assert "send_task" in session.events, "the answering task was never dispatched"
    assert session.events.index("commit") < session.events.index("send_task"), (
        f"dispatched before committing: {session.events} — the worker can win this race, find no "
        f"row, and return success on a question that will never be answered"
    )
    assert response["code"] == 202
    assert response["data"]["task_id"] == "task-1"


async def test_the_asker_is_recorded_on_the_question(monkeypatch, principal):
    """``asked_by`` is what the retention gate counts. A question with no asker is not use."""
    import app.celery_app as celery_module

    session = RecordingSession()
    monkeypatch.setattr(celery_module, "celery_app", RecordingCelery(session.events))

    await ask_question(
        AskRequest(text="질문", cell_id=uuid.uuid4()),
        session,
        principal,  # type: ignore[arg-type]
    )
    assert session.added[0].asked_by == principal.id
    assert session.added[0].cross_cell is False
