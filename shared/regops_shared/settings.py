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

    @property
    def sync_database_url(self) -> str:
        """Alembic runs sync; strip the async driver."""
        return self.database_url.replace("+asyncpg", "")


@lru_cache
def get_settings() -> Settings:
    return Settings()
