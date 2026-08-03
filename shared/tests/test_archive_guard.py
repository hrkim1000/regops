"""The WORM archive refuses a payload carrying a source credential.

ADR-0003 decision 13 was written about credentials going *out* — resolved URLs, log lines, stored
rows. The live API test of 2026-08-03 found the other direction: 국가법령정보's 목록 endpoints echo
the ``OC`` parameter back inside the response body, in ``행정규칙상세링크`` on every row.

That makes "never log the resolved URL" insufficient on its own. An archived response is immutable
by design, so a credential written there could never be removed — which is the exact property the
decision exists to prevent.
"""

from __future__ import annotations

import pytest

from regops_shared import storage
from regops_shared.settings import Settings
from regops_shared.storage import CredentialInArchiveError, archive_bytes

#: Recognisably fake. Real values live in .env and never in a test, a fixture, or a docstring.
FAKE_KEY = "not-a-real-key-xyz"


class _StubSettings:
    source_credentials = (FAKE_KEY,)


@pytest.fixture
def configured_credential(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the archive at a fake credential without touching the real Settings class."""
    monkeypatch.setattr(storage, "get_settings", lambda: _StubSettings())


# --- what counts as a credential ----------------------------------------------


def test_settings_expose_the_configured_credential() -> None:
    assert Settings(law_go_kr_oc="abc123").source_credentials == ("abc123",)


def test_an_unset_key_disables_the_check_rather_than_matching_everything() -> None:
    """An empty string is a substring of every payload. Filtering falsy values is what keeps an
    unconfigured environment from refusing to archive anything at all."""
    assert Settings(law_go_kr_oc=None).source_credentials == ()
    assert Settings(law_go_kr_oc="").source_credentials == ()


# --- the guard ----------------------------------------------------------------


@pytest.mark.usefixtures("configured_credential")
def test_archive_refuses_a_response_that_echoes_the_key() -> None:
    body = (
        f"<AdmRulSearch><admrul><link>/DRF/lawService.do?OC={FAKE_KEY}"
        "&amp;target=admrul</link></admrul></AdmRulSearch>"
    ).encode()
    with pytest.raises(CredentialInArchiveError):
        archive_bytes(body, content_type="application/xml")


@pytest.mark.usefixtures("configured_credential")
def test_refusal_happens_before_any_write() -> None:
    """No MinIO is reachable from the unit suite, so reaching the upload would raise a connection
    error instead. Getting CredentialInArchiveError proves the check runs first — which matters,
    because the archive is immutable and a late check would be no check at all."""
    with pytest.raises(CredentialInArchiveError):
        archive_bytes(f"OC={FAKE_KEY}".encode())


@pytest.mark.usefixtures("configured_credential")
def test_a_clean_payload_is_not_refused() -> None:
    """The counterpart: the guard must not reject ordinary 본문조회 responses, which is what the
    archive exists for. Verified live — none of the 13 archived documents contain the key."""
    from regops_shared.storage import _assert_no_credential

    _assert_no_credential("<법령><조문내용>제1조</조문내용></법령>".encode())
