"""Settings loaded from the environment. Never hard-code a credential."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from regops_shared.constants import EMBEDDING_DIM, EMBEDDING_MODEL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    stage: Literal["dev", "test", "prod"] = "dev"

    #: Which service this process is, reported to PostgreSQL as ``application_name``.
    #:
    #: Every service connects as the same role to the same database, so without this a connection
    #: log line names neither. It is what lets a dead backend's pid be traced back to an owner —
    #: see the ``db`` service's logging flags and the crashes of 2026-08-13 and 2026-08-27.
    service_name: str = "regops"

    # --- database ---------------------------------------------------------
    database_url: str = Field(
        default="postgresql+asyncpg://regops:regops@db:5432/regops",
        description="SQLAlchemy async DSN. The app role must NOT hold UPDATE/DELETE on audit_log.",
    )
    db_echo: bool = False

    # --- auth -------------------------------------------------------------
    jwt_secret: str = Field(
        default="change-me", description="HS256 signing key. Real value lives in .env"
    )
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # --- broker / storage -------------------------------------------------
    redis_url: str = "redis://redis:6379/0"
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "regops"
    minio_secret_key: str = "regops-secret"
    minio_secure: bool = False
    minio_bucket_prefix: str = "regops-"

    # --- LLM seam (ADR-0005 decision 7) -----------------------------------
    llm_provider: Literal["ollama", "claude"] = "ollama"
    ollama_base_url: str = "http://host.docker.internal:11434"
    ollama_model: str = "gemma3:2b"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5"

    #: Read by the client rather than hard-coded there. Extraction sends one clause; generation
    #: sends eight retrieved passages and asks for structured JSON back, and a small local model
    #: takes minutes over that. The old hard-coded 120s killed real answers mid-generation and
    #: surfaced as an httpx.ReadTimeout with no answer row, which reads like a bug in retrieval.
    llm_timeout_seconds: float = 180.0

    #: Ollama's context window for generation. **Not cosmetic**: a prompt longer than the window is
    #: silently truncated, and a generator that loses the tail of its passage list will cite a
    #: clause path it can no longer see — a fabricated citation manufactured by configuration
    #: rather than by the model. Null leaves Ollama's own default in place.
    ollama_num_ctx: int | None = None

    #: How many model layers Ollama must place on the GPU. Null leaves its own estimate in place.
    #:
    #: **A hardware knob, not a model property** — which is why it defaults to null and is set per
    #: deployment rather than pinned here. It changes nothing a model says: layer placement affects
    #: where the arithmetic happens, not its result, so ``llm_model`` and the IR fingerprint are
    #: untouched (ADR-0017 decision 1) and rows either side of the change stay comparable.
    #:
    #: It exists because Ollama's own estimate is conservative on a small card and the cost is
    #: paid per generated token. Measured 2026-09-03 on an RTX 3050 Laptop (4 GB) with
    #: ``gemma3:4b``, three samples each, on the generation half that is 86% of an extraction call
    #: — **at ``ollama_num_ctx=32768``, the value this stack actually sends.** That qualifier is
    #: the point: the first pass of this benchmark used Ollama's default 4096 window and would have
    #: recommended a placement whose KV cache does not fit what production asks for.
    #:
    #: ===============  ==============  ==========  ===========
    #: setting          generation      placement   VRAM
    #: ===============  ==============  ==========  ===========
    #: (null, auto)     18.1 tok/s      43% GPU     2,465 MiB
    #: 34               29.3 tok/s      77% GPU     3,029 MiB
    #: ===============  ==============  ==========  ===========
    #:
    #: 34 rather than full offload, which was 5% faster at 4096 but leaves under 500 MiB spare on a
    #: card the display also uses. An extraction runs for hours; a model that fails to load
    #: mid-corpus costs more than 5%. At 34 there is a gigabyte of headroom.
    ollama_num_gpu: int | None = None

    #: Embeddings are always Ollama and always this model/dim — changing them invalidates
    #: the whole index, so they are not configurable per provider.
    embedding_model: str = EMBEDDING_MODEL
    embedding_dim: int = EMBEDDING_DIM

    # --- source credentials (ADR-0003 decision 13) ------------------------
    #: 국가법령정보 OPEN API key. Self-designated by the account holder and passed as a
    #: query-string parameter, so it is likelier to be low-entropy and reused than an issued
    #: token — one leak is enough. It lives here and only here: never in import-source-map.md,
    #: never in a ``sources`` row, never in a fetch_observation, never in a fixture. The resolved
    #: URL is built at request time and is not persisted.
    law_go_kr_oc: str | None = None

    #: api.data.gov key for govinfo — the FD&C Act (USCODE) and Public Laws (PLAW), ADR-0018
    #: decision 12. Unlike the MFDS key this one is an issued token passed as ``?api_key=``, and
    #: govinfo does **not** echo it back in responses — checked across the collection, package and
    #: granule endpoints. It is still listed in :attr:`source_credentials` below: the archive
    #: refusing any payload that contains it costs nothing, and the day the API starts embedding it
    #: in a ``detailsLink`` is not a day anyone will notice in advance.
    #:
    #: ``DEMO_KEY`` works and is rate-limited to **10 requests an hour**, which is enough to probe
    #: and not enough to ingest — title 21 alone has 901 granules.
    govinfo_api_key: str | None = None

    # --- fetch politeness (ADR-0003 decision 9) ---------------------------
    http_timeout_seconds: float = 30.0
    http_max_retries: int = 4
    #: These are government hosts. Getting rate-limited off MFDS during the pilot would take out
    #: both gated cells at once.
    http_max_concurrency_per_host: int = 2

    @property
    def sync_database_url(self) -> str:
        """Alembic runs sync; strip the async driver."""
        return self.database_url.replace("+asyncpg", "")

    @property
    def source_credentials(self) -> tuple[str, ...]:
        """Every configured source credential, for code that must prove one is *absent*.

        The WORM archive uses this to refuse any payload containing one. That is not paranoia
        about our own logging: 국가법령정보 **echoes the ``OC`` parameter back inside the response
        body** — ``행정규칙상세링크`` on every 목록 row is a fully-formed URL with the key in it.
        Archiving such a response would write a credential into an immutable store, and the whole
        reason ADR-0003 decision 13 exists is that a credential written somewhere append-only can
        never be cleaned up.
        """
        return tuple(value for value in (self.law_go_kr_oc, self.govinfo_api_key) if value)


@lru_cache
def get_settings() -> Settings:
    return Settings()
