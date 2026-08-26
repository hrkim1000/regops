"""The IR serializer and the RBAC on locking.

Two things here are invariants rather than presentation:

- **``locked`` is the default listing filter.** A downstream consumer that forgets to filter must
  get ADR-0004 decision 4's behaviour anyway, because the failure mode is unreviewed model output
  being read as approved obligations.
- **A ``viewer`` cannot lock.** Locking is one of the two Phase 1 actions where a human assertion
  enters the audit trail (CLAUDE.md § Security), and the negative path is the half that actually
  needs a test.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest
from fastapi import HTTPException

from app.api.v1.irs import (
    RejectRequest,
    UnlockRequest,
    _ir_out,
    _run_out,
    lock_ir,
    reject_ir,
    unlock_ir,
)
from app.models import IR, ExtractionRun, IRCitation
from regops_shared.auth import Principal, require_roles
from regops_shared.constants import (
    IR_VISIBLE_STATUSES,
    Domain,
    ExtractionRunStatus,
    IRStatus,
    RejectionReason,
    Role,
)


def _ir(**overrides) -> IR:
    ir = IR(
        domain_profile=Domain.SAMD,
        bearer="제조업자",
        modal="하여야 한다",
        statement="기록을 3년간 보관",
        condition_text="2등급 이상 의료기기에 한정한다",
        taxonomy_code="design_control",
        status=IRStatus.DRAFT,
        llm_provider="ollama",
        llm_model="gemma3:2b",
        prompt_version="1.2.0",
        rule_version="1.2.0",
    )
    ir.id = uuid.uuid4()
    for key, value in overrides.items():
        setattr(ir, key, value)
    return ir


def _citation(**overrides) -> IRCitation:
    citation = IRCitation(
        ir_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_version_id=uuid.uuid4(),
        clause_path="제5조/제1항",
        effective_date=date(2026, 1, 1),
    )
    for key, value in overrides.items():
        setattr(citation, key, value)
    return citation


# --- serialization ------------------------------------------------------------------------------


def test_ir_carries_its_citation_and_its_provenance() -> None:
    """Both are mandatory reading: what it requires, on what authority, and who said so."""
    out = _ir_out(_ir(), [_citation()])

    assert out["citations"][0]["clause_path"] == "제5조/제1항"
    assert out["citations"][0]["effective_date"] == "2026-01-01"
    assert out["provenance"]["llm_provider"] == "ollama"
    assert out["provenance"]["llm_model"] == "gemma3:2b"
    assert out["provenance"]["rule_version"] == "1.2.0"


def test_class_restriction_rides_on_condition_text() -> None:
    """ADR-0017 decision 2 — one parameterised IR, not one per product class."""
    assert _ir_out(_ir(), [_citation()])["condition_text"] == "2등급 이상 의료기기에 한정한다"


@pytest.mark.parametrize(
    ("status", "visible"),
    [
        (IRStatus.DRAFT, False),
        (IRStatus.LOCKED, True),
        (IRStatus.STALE, False),
        (IRStatus.SUPERSEDED, False),
    ],
)
def test_only_locked_irs_report_as_visible_downstream(status, visible) -> None:
    """A draft IR is inert and a stale one has had its evidence amended out from under it."""
    assert _ir_out(_ir(status=status), [_citation()])["visible_downstream"] is visible
    assert (status in IR_VISIBLE_STATUSES) is visible


def test_superseded_citation_is_flagged_not_hidden() -> None:
    """The original stays resolvable (ADR-0002 decision 4); the flag is what changes."""
    superseded_at = datetime(2026, 8, 7, tzinfo=UTC)
    out = _ir_out(_ir(status=IRStatus.STALE), [_citation(superseded_at=superseded_at)])

    assert out["citations"][0]["superseded_at"] == superseded_at.isoformat()
    assert out["citations"][0]["clause_path"] == "제5조/제1항"


def test_supersession_chain_is_exposed() -> None:
    old = uuid.uuid4()
    out = _ir_out(_ir(supersedes_ir_id=old), [_citation()])
    assert out["supersedes_ir_id"] == str(old)


def test_run_reports_rejected_uncited_and_the_pinned_temperature() -> None:
    """Both are evidence: a climbing rejection rate is a prompt regression, and ADR-0017's
    determinism claim is only checkable if the temperature actually used is on the row."""
    run = ExtractionRun(
        document_version_id=uuid.uuid4(),
        domain_profile=Domain.COSMETIC,
        rule_version="1.2.0",
        prompt_version="1.2.0",
        llm_provider="ollama",
        llm_model="gemma3:2b",
        temperature=0.0,
        status=ExtractionRunStatus.COMPLETED,
        clauses_seen=120,
        irs_written=34,
        rejected_uncited=2,
        started_at=datetime(2026, 8, 7, tzinfo=UTC),
    )
    run.id = uuid.uuid4()
    out = _run_out(run)

    assert out["temperature"] == 0.0
    assert out["rejected_uncited"] == 2
    assert out["domain_profile"] == "cosmetic"


# --- RBAC and the lock lifecycle ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_viewer_cannot_lock_and_ra_can() -> None:
    """The negative path is the half that matters — locking is an assertion, not a state flip."""
    guard = require_roles([Role.RA, Role.ADMIN])
    viewer = Principal(id=uuid.uuid4(), email="viewer@example.test", role=Role.VIEWER)
    ra = Principal(id=uuid.uuid4(), email="ra@example.test", role=Role.RA)

    with pytest.raises(HTTPException) as exc:
        await guard(principal=viewer)
    assert exc.value.status_code == 403

    assert await guard(principal=ra) is ra


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [IRStatus.LOCKED, IRStatus.STALE, IRStatus.SUPERSEDED])
async def test_only_a_draft_can_be_locked(status) -> None:
    """Re-locking would overwrite the first signature; locking a stale IR would approve amended
    evidence; locking a superseded one would resurrect a replaced record."""
    ir = _ir(status=status)

    class _Db:
        async def get(self, _model, _id):
            return ir

    with pytest.raises(HTTPException) as exc:
        await lock_ir(
            ir.id,
            _Db(),  # type: ignore[arg-type]
            Principal(id=uuid.uuid4(), email="ra@example.test", role=Role.RA),
        )
    assert exc.value.status_code == 409
    assert status.value in exc.value.detail


# --- refusal, and taking back a lock (ADR-0020) -------------------------------------------------


class _Session:
    """Just enough session to drive a transition: one IR, and a record of what was committed."""

    def __init__(self, ir: IR) -> None:
        self._ir = ir
        self.committed = False
        self.audited: list[dict] = []

    async def get(self, _model, _id):
        return self._ir

    async def commit(self) -> None:
        self.committed = True


@pytest.fixture
def audit(monkeypatch):
    """Capture the audit append rather than writing a chain entry in a unit test."""
    entries: list[dict] = []

    async def _record(_db, **kwargs):
        entries.append(kwargs)
        return None

    monkeypatch.setattr("app.api.v1.irs.record", _record)
    return entries


@pytest.mark.asyncio
async def test_rejecting_a_draft_records_who_why_and_when(audit) -> None:
    """*ADR-0020 decision 1.* The point is that a refusal is **not** left as a draft: a draft that
    an RA has already refused reads as one nobody has opened, so it returns to the next reviewer
    forever and the agent's error rate has no denominator."""
    ir = _ir(status=IRStatus.DRAFT)
    db = _Session(ir)
    principal = Principal(id=uuid.uuid4(), email="ra@example.test", role=Role.RA)

    out = await reject_ir(
        ir.id,
        db,  # type: ignore[arg-type]
        principal,
        RejectRequest(
            reason=RejectionReason.NOT_AN_OBLIGATION,
            note="21 CFR 700.3(g) is a definition",
        ),
    )

    assert ir.status is IRStatus.REJECTED
    assert ir.rejected_by == principal.id
    assert ir.rejected_at is not None
    assert ir.rejection_reason is RejectionReason.NOT_AN_OBLIGATION
    assert ir.rejection_note
    assert db.committed
    assert out["data"]["status"] == "rejected"

    (entry,) = audit
    assert entry["action"] == "ir.rejected"
    # The agent's provenance rides along, because the count per reason is a signal about the
    # extraction regime rather than about this one IR.
    assert entry["payload"]["reason"] == "not_an_obligation"
    assert entry["payload"]["llm_model"] == ir.llm_model
    assert entry["payload"]["rule_version"] == ir.rule_version


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status", [IRStatus.LOCKED, IRStatus.STALE, IRStatus.SUPERSEDED, IRStatus.REJECTED]
)
async def test_only_a_draft_can_be_rejected(status, audit) -> None:
    """A locked IR is unlocked first — two steps, because taking back an approval and refusing a
    proposal are different assertions (*ADR-0020 decision 3*). Stale and superseded are already out
    of the queue, and re-rejecting would overwrite the first reviewer's reason."""
    ir = _ir(status=status)
    with pytest.raises(HTTPException) as exc:
        await reject_ir(
            ir.id,
            _Session(ir),  # type: ignore[arg-type]
            Principal(id=uuid.uuid4(), email="ra@example.test", role=Role.RA),
            RejectRequest(reason=RejectionReason.DUPLICATE, note="already covered"),
        )
    assert exc.value.status_code == 409
    assert status.value in exc.value.detail
    assert audit == []


@pytest.mark.asyncio
async def test_unlocking_returns_to_draft_and_clears_the_signature(audit) -> None:
    """*ADR-0020 decisions 3 and 4.* Back to `draft`, never straight to `rejected` — unlocking says
    the approval was a mistake, which is not the same as refusing the proposal.

    `locked_by` / `locked_at` clear because a draft that still names a signer is a lie about its own
    state; who signed it survives in the audit entry, which is append-only and hash-chained.
    """
    signer = uuid.uuid4()
    locked_at = datetime(2026, 8, 26, 4, 7, 9, tzinfo=UTC)
    ir = _ir(status=IRStatus.LOCKED, locked_by=signer, locked_at=locked_at)
    db = _Session(ir)

    out = await unlock_ir(
        ir.id,
        db,  # type: ignore[arg-type]
        Principal(id=uuid.uuid4(), email="ra@example.test", role=Role.RA),
        UnlockRequest(note="locked in error"),
    )

    assert ir.status is IRStatus.DRAFT
    assert ir.locked_by is None
    assert ir.locked_at is None
    assert out["data"]["locked_at"] is None
    assert db.committed

    (entry,) = audit
    assert entry["action"] == "ir.unlocked"
    assert entry["payload"]["previously_locked_by"] == str(signer)
    assert entry["payload"]["previously_locked_at"] == locked_at.isoformat()
    assert entry["payload"]["note"] == "locked in error"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [IRStatus.DRAFT, IRStatus.STALE, IRStatus.REJECTED])
async def test_only_a_locked_ir_can_be_unlocked(status, audit) -> None:
    ir = _ir(status=status)
    with pytest.raises(HTTPException) as exc:
        await unlock_ir(
            ir.id,
            _Session(ir),  # type: ignore[arg-type]
            Principal(id=uuid.uuid4(), email="ra@example.test", role=Role.RA),
            UnlockRequest(note="mis-click"),
        )
    assert exc.value.status_code == 409
    assert audit == []


@pytest.mark.asyncio
async def test_a_viewer_can_neither_reject_nor_unlock() -> None:
    """Both are human assertions entering the audit trail, so both carry the lock's guard."""
    guard = require_roles([Role.RA, Role.ADMIN])
    viewer = Principal(id=uuid.uuid4(), email="viewer@example.test", role=Role.VIEWER)
    with pytest.raises(HTTPException) as exc:
        await guard(principal=viewer)
    assert exc.value.status_code == 403


def test_a_rejected_ir_is_inert_exactly_as_a_draft_is() -> None:
    """*ADR-0020 decision 1.* `IR_VISIBLE_STATUSES` does not move: rejecting changes whether the
    refusal is recorded, not what flows downstream."""
    assert IRStatus.REJECTED not in IR_VISIBLE_STATUSES
    assert IR_VISIBLE_STATUSES == (IRStatus.LOCKED,)


def test_a_reason_is_required_and_a_blank_note_is_refused() -> None:
    """An unexplained reversal of a human assertion is the entry an auditor stops on."""
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        UnlockRequest(note="")
    with pytest.raises(pydantic.ValidationError):
        RejectRequest(reason=RejectionReason.DUPLICATE, note="")
