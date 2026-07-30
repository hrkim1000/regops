"""Phase 0 acceptance criteria, run against the live stack.

    docker compose --profile app up -d
    python -m pytest services/platform-core/tests/integration -q

These are the criteria in docs/plan/phase0_foundation.md. They assert the invariants structurally
rather than trusting that the code still does what it did when it was written.
"""

from __future__ import annotations

import os
from itertools import pairwise

import httpx
import pytest

BASE = os.environ.get("PLATFORM_CORE_URL", "http://localhost:28000")
API = f"{BASE}/api/v1"

ADMIN = ("admin@example.com", "Ph4se0-bootstrap!")
VIEWER = ("viewer@example.com", "Ph4se0-viewer!")

pytestmark = pytest.mark.integration


def _login(email: str, password: str) -> str:
    r = httpx.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    r.raise_for_status()
    return r.json()["data"]["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def admin_token() -> str:
    return _login(*ADMIN)


@pytest.fixture(scope="module")
def viewer_token() -> str:
    return _login(*VIEWER)


# --- stack health --------------------------------------------------------------


@pytest.mark.parametrize(
    ("service", "port"),
    [
        ("platform-core", 28000),
        ("regulation", 28001),
        ("monitoring", 28002),
        ("assistant", 28003),
    ],
)
def test_service_is_healthy_and_wears_the_envelope(service: str, port: int) -> None:
    body = httpx.get(f"http://localhost:{port}/health", timeout=10).json()
    assert set(body) == {"code", "status", "message", "data", "meta"}
    assert body["status"] == "success"
    assert body["data"]["service"] == service


# --- auth & RBAC ---------------------------------------------------------------


def test_login_issues_a_usable_token(admin_token: str) -> None:
    body = httpx.get(f"{API}/auth/me", headers=_auth(admin_token), timeout=10).json()
    assert body["data"]["email"] == ADMIN[0]
    assert body["data"]["role"] == "admin"


def test_missing_token_is_401() -> None:
    assert httpx.get(f"{API}/auth/me", timeout=10).status_code == 401


def test_wrong_password_is_401() -> None:
    r = httpx.post(f"{API}/auth/login", json={"email": VIEWER[0], "password": "wrong"}, timeout=10)
    assert r.status_code == 401


def test_viewer_cannot_create_users(viewer_token: str) -> None:
    """The RBAC negative path — viewer is read-only (ADR-0005 decision 5)."""
    r = httpx.post(
        f"{API}/users",
        headers=_auth(viewer_token),
        json={"email": "denied@example.com", "password": "x1234567", "role": "viewer"},
        timeout=10,
    )
    assert r.status_code == 403
    assert r.json()["status"] == "error"


def test_error_responses_also_wear_the_envelope(viewer_token: str) -> None:
    r = httpx.post(
        f"{API}/users",
        headers=_auth(viewer_token),
        json={"email": "denied@example.com", "password": "x1234567", "role": "viewer"},
        timeout=10,
    )
    assert set(r.json()) == {"code", "status", "message", "data", "meta"}
    assert r.json()["data"] is None


# --- audit chain (ADR-0011) ----------------------------------------------------


def test_audit_chain_is_intact(admin_token: str) -> None:
    body = httpx.post(f"{API}/audit/verify", headers=_auth(admin_token), timeout=30).json()
    assert body["data"]["intact"] is True, f"chain broken at seq {body['data']['first_bad_seq']}"


def test_audit_entries_link_to_their_predecessor(admin_token: str) -> None:
    entries = httpx.get(
        f"{API}/audit", headers=_auth(admin_token), params={"page_size": 200}, timeout=20
    ).json()["data"]
    assert entries, "expected at least one audit entry — login should have written one"
    for previous, current in pairwise(entries):
        assert current["prev_hash"] == previous["entry_hash"]


def test_login_is_audited(admin_token: str) -> None:
    entries = httpx.get(
        f"{API}/audit", headers=_auth(admin_token), params={"page_size": 200}, timeout=20
    ).json()["data"]
    assert any(e["action"] == "auth.login" for e in entries)


def test_viewer_cannot_verify_the_chain(viewer_token: str) -> None:
    r = httpx.post(f"{API}/audit/verify", headers=_auth(viewer_token), timeout=20)
    assert r.status_code == 403
