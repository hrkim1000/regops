"""Test helpers. Importable because ``conftest.py`` puts this directory on ``sys.path``."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.connectors.http import HttpResponse

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def fixture_bytes(name: str) -> bytes:
    """Recorded source responses. Connectors are never unit-tested against a live fetch —
    that is slow, flaky, credential-dependent, and impolite to a host that never agreed to be
    our CI runner."""
    return (FIXTURES / name).read_bytes()


def fixture_text(name: str) -> str:
    return fixture_bytes(name).decode("utf-8")


@dataclass
class StubFetcher:
    """Stands in for :class:`PoliteFetcher`, returning a recorded response.

    Records the conditional headers it was handed, so a test can assert cache validators are
    actually sent — a 304 is the cheapest observation there is, but only if we ask for one.
    """

    body: bytes = b""
    status: int = 200
    content_type: str = "application/xml"
    etag: str | None = None
    last_modified: str | None = None
    seen_etag: str | None = None
    seen_last_modified: str | None = None
    calls: int = 0

    def get(
        self,
        url: str,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> HttpResponse:
        self.calls += 1
        self.seen_etag = etag
        self.seen_last_modified = last_modified
        return HttpResponse(
            status=self.status,
            body=self.body,
            content_type=self.content_type,
            etag=self.etag,
            last_modified=self.last_modified,
        )

    def close(self) -> None:  # pragma: no cover - nothing to release
        pass


__all__ = ["FIXTURES", "StubFetcher", "fixture_bytes", "fixture_text"]
