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
    async def complete(self, prompt: str, *, system: str | None = None) -> Completion: ...

    @abstractmethod
    async def embed(self, text: str) -> list[float]: ...


class OllamaClient(LLMClient):
    provider = "ollama"

    def __init__(self, settings: Settings) -> None:
        self._base = settings.ollama_base_url.rstrip("/")
        self.model = settings.ollama_model
        self._embedding_model = settings.embedding_model

    async def complete(self, prompt: str, *, system: str | None = None) -> Completion:
        body: dict[str, object] = {"model": self.model, "prompt": prompt, "stream": False}
        if system:
            body["system"] = system
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(f"{self._base}/api/generate", json=body)
            response.raise_for_status()
            return Completion(
                text=response.json()["response"], provider=self.provider, model=self.model
            )

    async def embed(self, text: str) -> list[float]:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{self._base}/api/embeddings",
                json={"model": self._embedding_model, "prompt": text},
            )
            response.raise_for_status()
            return response.json()["embedding"]


class ClaudeClient(LLMClient):
    provider = "claude"

    def __init__(self, settings: Settings) -> None:
        if not settings.anthropic_api_key:
            raise ValueError("llm_provider='claude' requires anthropic_api_key")
        self._api_key = settings.anthropic_api_key
        self.model = settings.anthropic_model
        #: Embeddings never come from Claude — they stay pinned to Ollama.
        self._embedder = OllamaClient(settings)

    async def complete(self, prompt: str, *, system: str | None = None) -> Completion:
        body: dict[str, object] = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            body["system"] = system
        async with httpx.AsyncClient(timeout=120) as client:
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
