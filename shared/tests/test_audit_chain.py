"""Audit hash chain (ADR-0011). Pure-function tests — no DB."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from regops_shared.audit import compute_entry_hash, verify_chain
from regops_shared.constants import AUDIT_CHAIN_GENESIS


@dataclass
class FakeEntry:
    """Mirrors the AuditLog fields verify_chain reads."""

    seq: int
    actor_id: uuid.UUID | None
    service: str
    action: str
    entity_type: str | None
    entity_id: uuid.UUID | None
    payload: dict
    created_at: datetime
    prev_hash: str
    entry_hash: str


def _link(seq: int, prev_hash: str, *, action: str = "test.action") -> FakeEntry:
    fields = {
        "actor_id": None,
        "service": "platform-core",
        "action": action,
        "entity_type": None,
        "entity_id": None,
        "payload": {"n": seq},
        "created_at": datetime(2026, 7, 30, 12, seq, tzinfo=UTC),
        "prev_hash": prev_hash,
    }
    return FakeEntry(seq=seq, **fields, entry_hash=compute_entry_hash(**fields))


def _chain(length: int) -> list[FakeEntry]:
    entries: list[FakeEntry] = []
    prev = AUDIT_CHAIN_GENESIS
    for seq in range(1, length + 1):
        entry = _link(seq, prev)
        entries.append(entry)
        prev = entry.entry_hash
    return entries


def test_hash_is_deterministic() -> None:
    a, b = _link(1, AUDIT_CHAIN_GENESIS), _link(1, AUDIT_CHAIN_GENESIS)
    assert a.entry_hash == b.entry_hash


def test_intact_chain_verifies() -> None:
    assert verify_chain(_chain(5)) == (True, None)


def test_empty_chain_verifies() -> None:
    assert verify_chain([]) == (True, None)


def test_edited_payload_is_detected() -> None:
    """The whole point: a superuser edit that grants cannot prevent is still detectable."""
    entries = _chain(5)
    entries[2].payload = {"n": "tampered"}
    intact, first_bad = verify_chain(entries)
    assert not intact
    assert first_bad == 3


def test_deleted_row_breaks_the_link() -> None:
    entries = _chain(5)
    del entries[2]
    intact, first_bad = verify_chain(entries)
    assert not intact
    assert first_bad == 4


def test_rehashed_row_still_breaks_downstream() -> None:
    """Recomputing the edited row's own hash does not save the forger — every later prev_hash
    still points at the original."""
    entries = _chain(5)
    victim = entries[2]
    victim.action = "tampered.action"
    victim.entry_hash = compute_entry_hash(
        actor_id=victim.actor_id,
        service=victim.service,
        action=victim.action,
        entity_type=victim.entity_type,
        entity_id=victim.entity_id,
        payload=victim.payload,
        created_at=victim.created_at,
        prev_hash=victim.prev_hash,
    )
    intact, first_bad = verify_chain(entries)
    assert not intact
    assert first_bad == 4
