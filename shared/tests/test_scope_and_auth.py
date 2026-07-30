"""Scope invariants and auth primitives — the rules that must not drift."""

from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from regops_shared.auth import (
    Principal,
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)
from regops_shared.constants import CELL_COUNT, CELLS, Authority, Domain, Role
from regops_shared.models import Cell


def test_exactly_eight_cells() -> None:
    assert len(CELLS) == CELL_COUNT == 8
    assert len(set(CELLS)) == 8


def test_no_authority_outside_scope() -> None:
    assert {a.value for a in Authority} == {"mfds", "fda", "eu", "nmpa"}


def test_no_domain_outside_scope() -> None:
    """Never "Medical Device", "Device", or "MDR" as a domain value."""
    assert {d.value for d in Domain} == {"samd", "cosmetic"}


def test_cell_slug_spelling() -> None:
    assert Cell.make_slug(Authority.MFDS, Domain.SAMD) == "mfds_samd"
    assert Cell.make_slug(Authority.EU, Domain.COSMETIC) == "eu_cosmetic"


def test_phase1_roles_only() -> None:
    """`developer`, `qa` and `clinical_expert` are prior-platform roles and do not apply."""
    assert {r.value for r in Role} == {"viewer", "ra", "admin"}


def test_password_round_trip() -> None:
    hashed = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", hashed)
    assert not verify_password("wrong", hashed)


def test_token_carries_required_claims() -> None:
    user_id = uuid.uuid4()
    token, jti, expires_at = create_access_token(
        user_id=user_id, email="ra@example.com", role=Role.RA
    )
    payload = decode_token(token)
    for claim in ("id", "email", "role", "exp", "type"):
        assert claim in payload
    assert payload["id"] == str(user_id)
    assert payload["role"] == "ra"
    assert payload["jti"] == jti
    assert expires_at is not None


def test_tampered_token_rejected() -> None:
    token, _, _ = create_access_token(user_id=uuid.uuid4(), email="a@example.com", role=Role.VIEWER)
    with pytest.raises(HTTPException) as exc:
        decode_token(token[:-4] + "AAAA")
    assert exc.value.status_code == 401


@pytest.mark.parametrize(
    ("actual", "required", "allowed"),
    [
        (Role.VIEWER, Role.VIEWER, True),
        (Role.VIEWER, Role.RA, False),
        (Role.RA, Role.RA, True),
        (Role.RA, Role.ADMIN, False),
        (Role.ADMIN, Role.RA, True),
    ],
)
def test_role_hierarchy(actual: Role, required: Role, allowed: bool) -> None:
    principal = Principal(id=uuid.uuid4(), email="u@example.com", role=actual)
    assert principal.has_at_least(required) is allowed
