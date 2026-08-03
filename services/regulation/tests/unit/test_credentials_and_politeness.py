"""Credentials never reach a stored URL, a log line, or a fixture (ADR-0003 decision 13).

The audit trail is append-only and outlives any key rotation, and Phase 3 exports it to customers.
A credential written into it cannot be cleaned up — and because the 국가법령정보 key is
*self-chosen* rather than issued, it is likelier to be low-entropy and reused. One leak is enough.
"""

from __future__ import annotations

import inspect

import pytest

from app.connectors.base import MissingCredentialError
from app.connectors.http import redact_url, resolve_url
from app.seed import SEED
from regops_shared.constants import CREDENTIAL_PLACEHOLDER
from regops_shared.models import FetchObservation


def test_resolved_url_requires_the_key_rather_than_fetching_without_it() -> None:
    """An unauthenticated request returns HTTP 200 with an error body, so proceeding without a key
    would record a healthy-looking observation for a fetch that retrieved nothing."""
    with pytest.raises(MissingCredentialError):
        resolve_url("https://example.invalid/x?OC={OC}", credential=None)


def test_resolution_substitutes_only_the_placeholder() -> None:
    resolved = resolve_url("https://example.invalid/x?OC={OC}&target=law", credential="secret")
    assert resolved == "https://example.invalid/x?OC=secret&target=law"


def test_template_without_a_placeholder_is_untouched() -> None:
    url = "https://www.mfds.go.kr/www/rss/list.do"
    assert resolve_url(url) == url


@pytest.mark.parametrize("param", ["OC", "oc", "key", "apikey", "api_key"])
def test_redaction_covers_every_credential_parameter(param: str) -> None:
    redacted = redact_url(f"https://example.invalid/x?{param}=supersecret&target=law")
    assert "supersecret" not in redacted
    assert "REDACTED" in redacted
    assert "target=law" in redacted


def test_redaction_leaves_ordinary_urls_alone() -> None:
    url = "https://www.mfds.go.kr/brd/m_207/list.do?page=2"
    assert redact_url(url) == url


def test_fetch_observations_cannot_store_a_request_url() -> None:
    """Structural, not conventional: there is no column to put one in."""
    columns = {c.name for c in FetchObservation.__table__.columns}
    for forbidden in ("url", "request_url", "resolved_url", "source_url", "endpoint"):
        assert forbidden not in columns, (
            f"{forbidden!r} would let a resolved URL — and with it a credential — into the "
            "append-only trail, where it could never be cleaned up"
        )


def test_seeded_templates_carry_a_placeholder_not_a_key() -> None:
    for row in SEED:
        if row.url_template and "law.go.kr" in row.url_template:
            assert CREDENTIAL_PLACEHOLDER in row.url_template, (
                f"{row.slug}: an authenticated source must template its credential"
            )
        if row.url_template:
            assert "OC=" not in row.url_template.replace(f"OC={CREDENTIAL_PLACEHOLDER}", "")


def test_no_seeded_row_carries_a_credential_in_params() -> None:
    for row in SEED:
        for key, value in row.params.items():
            assert key.lower() not in {"oc", "key", "apikey", "api_key"}
            assert CREDENTIAL_PLACEHOLDER not in str(value)


def test_http_module_does_not_return_the_resolved_url() -> None:
    """The resolved value is used immediately and never leaves the module — it is not attached to
    the response object, so nothing downstream can accidentally persist it."""
    from app.connectors.http import HttpResponse

    fields = set(inspect.signature(HttpResponse).parameters)
    assert "url" not in fields
