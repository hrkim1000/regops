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

from app.api.v1.irs import _ir_out, _run_out, lock_ir
from app.models import IR, ExtractionRun, IRCitation
from regops_shared.auth import Principal, require_roles
from regops_shared.constants import (
    IR_VISIBLE_STATUSES,
    Domain,
    ExtractionRunStatus,
    IRStatus,
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
