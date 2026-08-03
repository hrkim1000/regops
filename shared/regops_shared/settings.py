"""Settings loaded from the environment. Never hard-code a credential."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from regops_shared.constants import EMBEDDING_DIM, EMBEDDING_MODEL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    stage: Literal["dev", "test", "prod"] = "dev"

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
        return tuple(value for value in (self.law_go_kr_oc,) if value)


@lru_cache
def get_settings() -> Settings:
    return Settings()
