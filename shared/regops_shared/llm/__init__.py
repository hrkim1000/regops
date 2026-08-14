"""The pluggable LLM seam (ADR-0005 decision 7).

Swapping Ollama for Claude must not require touching a service. Every client reports
``provider``/``model`` so any row an LLM produced can record what produced it — the provenance
convention that ADR-0008's agent/pipeline split rests on.

Embeddings are always Ollama ``nomic-embed-text`` 768-dim regardless of the generation provider,
because changing them invalidates the whole index.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx

from regops_shared.settings import Settings, get_settings


@dataclass(frozen=True, slots=True)
class Completion:
    text: str
    provider: str
    model: str


class LLMClient(ABC):
    provider: str
    model: str

    @abstractmethod
    async def complete(
        self, prompt: str, *, system: str | None = None, temperature: float | None = None
    ) -> Completion: ...

    @abstractmethod
    async def embed(self, text: str) -> list[float]: ...


class OllamaClient(LLMClient):
    provider = "ollama"

    def __init__(self, settings: Settings) -> None:
        self._base = settings.ollama_base_url.rstrip("/")
        self.model = settings.ollama_model
        self._embedding_model = settings.embedding_model
        self._timeout = settings.llm_timeout_seconds
        self._num_ctx = settings.ollama_num_ctx

    async def complete(
        self, prompt: str, *, system: str | None = None, temperature: float | None = None
    ) -> Completion:
        body: dict[str, object] = {"model": self.model, "prompt": prompt, "stream": False}
        if system:
            body["system"] = system
        # Ollama takes sampling parameters under `options`, not at the top level; a stray
        # top-level `temperature` is silently ignored, which would make a pinned-to-zero run
        # look deterministic while sampling normally.
        options: dict[str, object] = {}
        if temperature is not None:
            options["temperature"] = temperature
        if self._num_ctx:
            # A prompt longer than the window is truncated without an error, and a generator that
            # loses the tail of its passage list cites what it can no longer see.
            options["num_ctx"] = self._num_ctx
        if options:
            body["options"] = options
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(f"{self._base}/api/generate", json=body)
            response.raise_for_status()
            return Completion(
                text=response.json()["response"], provider=self.provider, model=self.model
            )

    async def embed(self, text: str) -> list[float]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base}/api/embeddings",
                json={"model": self._embedding_model, "prompt": text},
            )
            response.raise_for_status()
            return response.json()["embedding"]


class ClaudeClient(LLMClient):
    """The Anthropic arm of the seam. **Known defect: it does not run as written.**

    ``complete()`` sends ``temperature`` whenever the caller passes one, and both callers do —
    extraction and generation are pinned to ``0.0`` by ADR-0017 decision 1. Current Opus- and
    Sonnet-tier models **reject ``temperature`` with a 400**, so ``LLM_PROVIDER=claude`` fails on
    its first generation call. The pinned model in ``.env.dev`` is one of them.

    Recorded rather than fixed on 2026-08-14 (phase1.6 deviation 13): the pinned regime is
    ``ollama``/``gemma3:4b``, so nothing currently measured is affected, and a phase being closed is
    the wrong moment to add an unexercised code path. It becomes blocking the moment anyone runs the
    Anthropic provider as the comparison regime phase1.6 recommends — which is when it would
    otherwise be found, mid-run, as a 400 per item. The fix is to drop ``temperature`` for models
    that reject it and to update the pinned model id; determinism then comes from the prompt and the
    recorded regime rather than from a sampling parameter that no longer exists.
    """

    provider = "claude"

    def __init__(self, settings: Settings) -> None:
        if not settings.anthropic_api_key:
            raise ValueError("llm_provider='claude' requires anthropic_api_key")
        self._api_key = settings.anthropic_api_key
        self.model = settings.anthropic_model
        self._timeout = settings.llm_timeout_seconds
        #: Embeddings never come from Claude — they stay pinned to Ollama.
        self._embedder = OllamaClient(settings)

    async def complete(
        self, prompt: str, *, system: str | None = None, temperature: float | None = None
    ) -> Completion:
        body: dict[str, object] = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            body["system"] = system
        if temperature is not None:
            body["temperature"] = temperature
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                json=body,
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
            )
            response.raise_for_status()
            blocks = response.json()["content"]
            text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
            return Completion(text=text, provider=self.provider, model=self.model)

    async def embed(self, text: str) -> list[float]:
        return await self._embedder.embed(text)


def get_llm_client(settings: Settings | None = None) -> LLMClient:
    """Resolve the configured provider. A service-local override must not touch the global one."""
    settings = settings or get_settings()
    match settings.llm_provider:
        case "ollama":
            return OllamaClient(settings)
        case "claude":
            return ClaudeClient(settings)
        case unknown:  # pragma: no cover - guarded by Literal
            raise ValueError(f"Unknown llm_provider: {unknown}")


__all__ = ["ClaudeClient", "Completion", "LLMClient", "OllamaClient", "get_llm_client"]
