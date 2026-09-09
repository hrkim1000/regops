"""What the Ollama client actually puts on the wire.

Every one of these options is silently ignored if it lands in the wrong place — Ollama reads
sampling and runtime parameters from ``options``, not from the request body — so "we set it" is not
a claim any code path checks. A pinned temperature that never arrived would make a sampling run look
deterministic (ADR-0017 decision 1); an unsent ``num_predict`` would leave generation unbounded and
bring back the failure it exists to stop.

No network: ``httpx.AsyncClient`` is replaced with a recorder, which is also why this belongs in
``shared`` rather than in a service — the seam is what is under test, not any caller of it.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pytest

from regops_shared.llm import OllamaClient
from regops_shared.settings import Settings


class _Response:
    status_code = 200

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


class _RecordingClient:
    """Stands in for ``httpx.AsyncClient``, keeping the body of the one call made through it."""

    sent: ClassVar[dict[str, Any]] = {}
    timeout: ClassVar[float | None] = None

    def __init__(self, timeout: float | None = None) -> None:
        type(self).timeout = timeout

    async def __aenter__(self) -> _RecordingClient:
        return self

    async def __aexit__(self, *_exc: object) -> bool:
        return False

    async def post(self, url: str, json: dict[str, Any]) -> _Response:
        # `json` shadows the module, matching httpx's own parameter name — the call site is what
        # this test exists to mirror.
        type(self).sent = json
        return _Response({"response": "[]"})


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> type[_RecordingClient]:
    _RecordingClient.sent = {}
    monkeypatch.setattr("regops_shared.llm.httpx.AsyncClient", _RecordingClient)
    return _RecordingClient


def _settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "llm_provider": "ollama",
        "ollama_base_url": "http://ollama:11434",
        "ollama_model": "gemma3:4b",
        "ollama_num_ctx": 32768,
        "ollama_num_gpu": 34,
    }
    base.update(overrides)
    return Settings(**base)


@pytest.mark.asyncio
async def test_generation_is_bounded_so_one_clause_cannot_take_the_run_down(recorder) -> None:
    """``num_predict`` reaches Ollama, under ``options`` where Ollama reads it.

    Unbounded, a model that stops emitting a stop token generates until ``num_ctx`` fills. Measured
    on gemma3:4b 2026-09-09: healthy extraction replies were 200-400 tokens in 8-13s, while three
    clauses of the 전자파 시험방법 annexes ran to 1,200-1,400 and one to 4,956 — past the 180s
    budget, so `httpx.ReadTimeout` killed the whole run. Token rate never changed; the model was not
    slow, it would not stop.
    """
    client = OllamaClient(_settings(ollama_num_predict=1024))
    await client.complete("prompt", temperature=0.0)

    options = recorder.sent["options"]
    assert options["num_predict"] == 1024, "an unsent cap is the same as no cap"
    assert "num_predict" not in recorder.sent, "a top-level parameter is silently ignored by Ollama"


@pytest.mark.asyncio
async def test_a_null_cap_sends_nothing_rather_than_a_zero(recorder) -> None:
    """``None`` means "leave Ollama's own default alone", and 0 would mean "generate nothing"."""
    client = OllamaClient(_settings(ollama_num_predict=None))
    await client.complete("prompt", temperature=0.0)

    assert "num_predict" not in recorder.sent.get("options", {})


@pytest.mark.asyncio
async def test_the_pinned_temperature_and_window_travel_with_it(recorder) -> None:
    """The cap must not have displaced the options that were already load-bearing.

    ``temperature`` is ADR-0017 decision 1 and ``num_ctx`` guards against a prompt truncated before
    the model sees its passage list — a fabricated citation manufactured by configuration.
    """
    client = OllamaClient(_settings(ollama_num_predict=1024))
    await client.complete("prompt", system="rules", temperature=0.0)

    options = recorder.sent["options"]
    assert options["temperature"] == 0.0
    assert options["num_ctx"] == 32768
    assert options["num_gpu"] == 34
    assert recorder.sent["system"] == "rules"
    assert recorder.sent["stream"] is False
