"""Configuration, read entirely from environment variables.

Nothing secret is hardcoded. On a deployed host you set GEMINI_API_KEY in the
platform's environment; locally you put it in a .env file (git-ignored).
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Gemini
    gemini_api_key: str = ""
    generation_model: str = "gemini-2.5-flash"
    embedding_model: str = "text-embedding-004"
    embedding_dim: int = 768

    # Embeddings: "gemini" (default) or "local" (sentence-transformers fallback).
    embedding_provider: str = "gemini"
    local_embedding_model: str = "all-MiniLM-L6-v2"  # 384 dims, used only if provider=local

    # Database
    database_url: str = "postgresql://postgres:postgres@localhost:5432/mna"

    # Retrieval
    top_k: int = 5
    candidate_k: int = 20            # over-fetch, then merge/rerank
    max_answer_sentences: int = 4    # Rule 4

    # Ingestion
    guidelines_dir: str = "data/guidelines"
    chunk_chars: int = 1100
    chunk_overlap: int = 180

    # Simple guard for the admin ingest endpoint.
    admin_token: str = "change-me"


@lru_cache
def get_settings() -> Settings:
    return Settings()
