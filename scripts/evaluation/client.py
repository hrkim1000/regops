"""HTTP access to the four services, for the measurements a service owns.

The split with :mod:`.corpus` is deliberate. Anything a service *computes* — submission-requirement
detection, alert coverage, the "needs verification" rate — is read through its endpoint, so the
harness scores the same logic a user sees rather than a second implementation that could agree with
the plan while disagreeing with the product. Anything that is a plain stored fact with no endpoint —
poll schedules, IR counts per clause — is read from the database.

The token is **minted, not logged in for**. The harness runs inside the stack, where ``JWT_SECRET``
is already present and verification is stateless per service, so asking `platform-core` for a token
would mean putting a password in a script to obtain a credential the process can already produce.
It is minted for a *real* ``users`` row looked up by email, so ``queries.asked_by`` references a
principal that exists and the audit trail names a person rather than a synthetic id.
"""

from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass
from typing import Any

import httpx

from regops_shared.auth import create_access_token
from regops_shared.constants import Role

#: Compose service names. Overridable so the harness can be pointed at a deployed stack.
DEFAULT_URLS = {
    "platform-core": "http://platform-core:8000",
    "regulation": "http://regulation:8000",
    "monitoring": "http://monitoring:8000",
    "assistant": "http://assistant:8000",
}

#: A question is model-bound: one generation plus one verification per claim, measured at 112
#: seconds for a real question against the local model. The ceiling is generous on purpose — a
#: harness that gave up early would record an infrastructure failure as a product refusal.
DEFAULT_ANSWER_TIMEOUT_SECONDS = 600
POLL_INTERVAL_SECONDS = 5


class EvaluationError(RuntimeError):
    """Something the harness could not do. Never conflated with the product declining to answer."""


@dataclass(frozen=True, slots=True)
class Services:
    token: str
    urls: dict[str, str]
    timeout: float = 60.0

    def url(self, service: str, path: str) -> str:
        base = self.urls.get(service) or DEFAULT_URLS[service]
        return f"{base.rstrip('/')}{path}"

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


def connect(*, user_id: uuid.UUID, email: str, role: Role) -> Services:
    token, _, _ = create_access_token(user_id=user_id, email=email, role=role)
    urls = {
        name: os.environ.get(f"{name.upper().replace('-', '_')}_URL", default)
        for name, default in DEFAULT_URLS.items()
    }
    return Services(token=token, urls=urls)


def _unwrap(response: httpx.Response) -> Any:
    """Every response wears the envelope, so every read unwraps it in exactly one place."""
    if response.status_code >= 400:
        raise EvaluationError(
            f"{response.request.method} {response.request.url} → "
            f"{response.status_code} {response.text[:200]}"
        )
    payload = response.json()
    if not isinstance(payload, dict) or "data" not in payload:
        raise EvaluationError(f"{response.request.url} returned no envelope")
    if payload.get("status") == "error":
        raise EvaluationError(f"{response.request.url} → {payload.get('message')}")
    return payload["data"]


def get(services: Services, service: str, path: str, **params: Any) -> Any:
    with httpx.Client(timeout=services.timeout) as client:
        return _unwrap(
            client.get(
                services.url(service, path),
                headers=services.headers,
                params={key: value for key, value in params.items() if value is not None},
            )
        )


def post(services: Services, service: str, path: str, body: dict[str, Any] | None = None) -> Any:
    with httpx.Client(timeout=services.timeout) as client:
        return _unwrap(
            client.post(services.url(service, path), headers=services.headers, json=body or {})
        )


def ask(
    services: Services, *, question: str, cell_id: uuid.UUID, cross_cell: bool = False
) -> uuid.UUID:
    data = post(
        services,
        "assistant",
        "/api/v1/queries",
        {"text": question, "cell_id": str(cell_id), "cross_cell": cross_cell},
    )
    return uuid.UUID(str(data["id"]))


def await_answer(
    services: Services,
    query_id: uuid.UUID,
    *,
    timeout_seconds: int = DEFAULT_ANSWER_TIMEOUT_SECONDS,
) -> tuple[dict[str, Any], float]:
    """Poll until the worker lands an answer. Returns ``(answer, elapsed_seconds)``.

    A timeout raises rather than returning a refusal-shaped result. The distinction is the whole
    reason ``ObservedAnswer.error`` exists: a question the harness never got an answer to is not
    the product declining, and folding the two together moves the refusal rate in the direction
    that looks healthy.
    """
    started = time.monotonic()
    deadline = started + timeout_seconds
    while time.monotonic() < deadline:
        data = get(services, "assistant", f"/api/v1/queries/{query_id}")
        answer = data.get("answer")
        if answer is not None:
            return answer, time.monotonic() - started
        time.sleep(POLL_INTERVAL_SECONDS)
    raise EvaluationError(
        f"query {query_id} produced no answer within {timeout_seconds}s — recorded as a harness "
        f"error, not as a refusal"
    )


def answer_metrics(services: Services) -> dict[str, Any]:
    return get(services, "assistant", "/api/v1/metrics/answers")


def alert_metrics(services: Services, *, days: int) -> dict[str, Any]:
    return get(services, "monitoring", "/api/v1/metrics/alerts", days=days)


def submission_requirements(services: Services, version_id: uuid.UUID) -> list[dict[str, Any]]:
    data = get(
        services, "regulation", f"/api/v1/document-versions/{version_id}/submission-requirements"
    )
    if isinstance(data, dict):
        return list(data.get("requirements") or [])
    return list(data or [])


__all__ = [
    "DEFAULT_ANSWER_TIMEOUT_SECONDS",
    "DEFAULT_URLS",
    "EvaluationError",
    "Services",
    "alert_metrics",
    "answer_metrics",
    "ask",
    "await_answer",
    "connect",
    "get",
    "post",
    "submission_requirements",
]
