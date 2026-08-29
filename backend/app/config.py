"""Application configuration, loaded from environment / .env.

Everything that varies between environments (secrets, model names, thresholds)
lives here so the rest of the code can import a single typed ``settings``.
"""
from __future__ import annotations

from functools import lru_cache

from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- GitHub (read-only) ----
    github_token: str = Field(default="", alias="GITHUB_TOKEN")
    github_api_base: str = Field(default="https://api.github.com", alias="GITHUB_API_BASE")

    # ---- LLM: Gemini ----
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-2.5-pro", alias="GEMINI_MODEL")
    gemini_verify_model: str = Field(default="gemini-2.5-flash", alias="GEMINI_VERIFY_MODEL")

    # ---- Embeddings (local sentence-transformers) ----
    embedding_model: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2", alias="EMBEDDING_MODEL"
    )
    # Must match the vector(N) width in the migration.
    embedding_dim: int = Field(default=384, alias="EMBEDDING_DIM")

    # ---- Database ----
    database_url: str = Field(
        default="postgresql+psycopg2://prr:prr@localhost:5432/prr",
        alias="DATABASE_URL",
    )

    # ---- RAG / pipeline ----
    retrieval_top_k: int = Field(default=8, alias="RETRIEVAL_TOP_K")
    confidence_threshold: float = Field(default=0.55, alias="CONFIDENCE_THRESHOLD")

    # ---- App ----
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    cors_origins: str = Field(default="http://localhost:5173", alias="CORS_ORIGINS")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached accessor so we parse the environment exactly once."""
    return Settings()


settings = get_settings()
