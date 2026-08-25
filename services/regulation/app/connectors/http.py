"""Polite HTTP fetching, and the one place a credential is ever resolved into a URL.

Politeness is part of the contract, not optional courtesy (ADR-0003 decision 9): these are
government hosts, and getting rate-limited off MFDS during the pilot would take out both gated
cells at once. Phase 3 also sells to customers who will ask how we collect.

The credential rule (ADR-0003 decision 13) is enforced here by there being exactly one function
that can produce a resolved URL, and one that must be applied before any URL is logged. The
resolved value never leaves this module: it is not returned, not stored, and not attached to the
response object.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from threading import Lock
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
import structlog

from regops_shared.constants import (
    CREDENTIAL_PARAMS,
    CREDENTIAL_PLACEHOLDER,
    HOST_MIN_INTERVAL_SECONDS,
    USER_AGENT,
)
from regops_shared.settings import get_settings

from .base import ConnectorError, MissingCredentialError

log = structlog.get_logger(__name__)

#: Statuses worth another attempt. Everything else is a real answer, including 404.
RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})


def redact_url(url: str) -> str:
    """Blank any credential parameter so a URL is safe to log or store.

    The audit trail is append-only and outlives key rotation; a credential written into it cannot
    be cleaned up, and Phase 3 exports the trail to customers.
    """
    parts = urlsplit(url)
    if not parts.query:
        return url
    query = [
        (key, "REDACTED" if key in CREDENTIAL_PARAMS else value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
    ]
    return urlunsplit(parts._replace(query=urlencode(query)))


def resolve_url(template: str, *, credential: str | None = None) -> str:
    """Substitute the credential placeholder. The result is used immediately and never persisted.

    Raises rather than fetching without a key: an unauthenticated request to 국가법령정보 returns
    HTTP 200 with an error body, so silently proceeding would record a healthy-looking observation
    for a fetch that retrieved nothing.
    """
    if CREDENTIAL_PLACEHOLDER not in template:
        return template
    if not credential:
        raise MissingCredentialError(
            "url_template needs a credential that settings do not carry — set LAW_GO_KR_OC in "
            ".env (never in the sources row, the source map, or a fixture)"
        )
    return template.replace(CREDENTIAL_PLACEHOLDER, credential)


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status: int
    body: bytes
    content_type: str
    etag: str | None = None
    last_modified: str | None = None

    @property
    def not_modified(self) -> bool:
        return self.status == 304


class _HostThrottle:
    """Minimum gap between two requests to the same host.

    Process-local, which is exact for the Phase 1 topology (one `regulation` worker) and
    approximate beyond it. When a second worker is added, this moves to a Redis-backed gate — the
    per-task rate limit on the Celery side is the other half of the same budget.
    """

    def __init__(self, min_interval: float = HOST_MIN_INTERVAL_SECONDS) -> None:
        self._min_interval = min_interval
        self._last: dict[str, float] = {}
        self._lock = Lock()

    def wait(self, host: str) -> None:
        with self._lock:
            now = time.monotonic()
            earliest = self._last.get(host, 0.0) + self._min_interval
            delay = max(0.0, earliest - now)
            self._last[host] = now + delay
        if delay:
            time.sleep(delay)


_throttle = _HostThrottle()


class PoliteFetcher:
    """Identifies itself, cache-validates, backs off, and never logs a resolved URL."""

    def __init__(self, client: httpx.Client | None = None) -> None:
        settings = get_settings()
        self._timeout = settings.http_timeout_seconds
        self._max_retries = settings.http_max_retries
        self._client = client or httpx.Client(
            timeout=self._timeout,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> PoliteFetcher:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def get(
        self,
        url: str,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> HttpResponse:
        """GET with conditional headers and exponential backoff.

        A 304 is the cheapest possible ``fetch_observation``: we proved the source was checked
        without transferring or hashing anything.

        ``extra_headers`` exists for **credentials that must not travel in a URL**. api.govinfo.gov
        accepts its key either as an ``api_key`` query parameter or as ``X-Api-Key``, and the query
        form would put a live credential into ``sources.url_template``, into every log line that
        echoes a URL, and into any error we report. The header form keeps it in the request only.
        ``redact_url`` covers what does end up in a URL elsewhere; this covers what never should.
        """
        headers: dict[str, str] = dict(extra_headers or {})
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified

        safe_url = redact_url(url)
        host = urlsplit(url).netloc
        last_error: Exception | None = None

        for attempt in range(self._max_retries):
            _throttle.wait(host)
            try:
                response = self._client.get(url, headers=headers)
            except httpx.HTTPError as exc:
                last_error = exc
                log.warning("fetch.transport_error", url=safe_url, attempt=attempt, error=str(exc))
            else:
                if response.status_code not in RETRYABLE_STATUSES:
                    return HttpResponse(
                        status=response.status_code,
                        body=response.content,
                        content_type=response.headers.get("content-type", ""),
                        etag=response.headers.get("etag"),
                        last_modified=response.headers.get("last-modified"),
                    )
                last_error = ConnectorError(f"HTTP {response.status_code}")
                log.warning(
                    "fetch.retryable_status",
                    url=safe_url,
                    status=response.status_code,
                    attempt=attempt,
                )
                retry_after = _parse_retry_after(response.headers.get("retry-after"))
                if retry_after is not None:
                    time.sleep(retry_after)
                    continue

            # Exponential backoff with jitter — a fleet retrying in lockstep is its own outage.
            time.sleep(min(60.0, 2**attempt) * (0.5 + random.random()))

        raise ConnectorError(f"{safe_url}: giving up after {self._max_retries} attempts") from (
            last_error
        )


def _parse_retry_after(value: str | None) -> float | None:
    """Honour ``Retry-After`` when it is a delay in seconds. A HTTP-date form falls back to
    ordinary backoff rather than being mis-parsed into a multi-hour sleep."""
    if not value:
        return None
    try:
        return max(0.0, min(300.0, float(value)))
    except ValueError:
        return None


__all__ = [
    "RETRYABLE_STATUSES",
    "HttpResponse",
    "PoliteFetcher",
    "redact_url",
    "resolve_url",
]
