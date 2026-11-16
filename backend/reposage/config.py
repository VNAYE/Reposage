"""Application settings, loaded from environment variables / .env."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Every knob the app has. Override any field with an upper-case env var."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "RepoSage"
    environment: str = "development"
    log_level: str = "INFO"

    # --- providers ---------------------------------------------------------
    gemini_api_key: str = ""
    chat_provider: str = "gemini"
    embedding_provider: str = "gemini"
    chat_model: str = "gemini-3.5-flash-lite"
    chat_fallback_models: str = "gemini-3.1-flash-lite"
    gemini_retry_attempts: int = 2
    chat_first_token_timeout: float = 10.0
    chat_stream_idle_timeout: float = 30.0
    chat_stream_timeout: float = 90.0
    chat_request_timeout: float = 30.0
    embedding_model: str = "gemini-embedding-001"
    embedding_dim: int = 768
    temperature: float = 0.2
    max_output_tokens: int = 2048

    # --- storage -----------------------------------------------------------
    storage_backend: str = "postgres"
    metrics_backend: str = "auto"
    database_url: str = "postgresql://reposage:reposage@localhost:5432/reposage"
    local_index_path: str = "./data/index.json"
    db_pool_min: int = 1
    db_pool_max: int = 10

    # --- retrieval ---------------------------------------------------------
    retrieval_top_k: int = 10
    vector_candidates: int = 40
    keyword_candidates: int = 40
    rrf_k: int = 60
    reranker: str = "heuristic"
    rerank_candidates: int = 24

    # --- ingestion ---------------------------------------------------------
    github_token: str = ""
    max_file_bytes: int = 200_000
    max_files: int = 800
    max_chunks: int = 1500
    chunk_max_lines: int = 80
    chunk_overlap_lines: int = 10
    chunker: str = "code"
    embed_batch_size: int = 16
    embedding_tokens_per_minute: int = 30_000

    # --- guardrails / verification ----------------------------------------
    max_question_chars: int = 2000
    injection_action: str = "block"
    verify_answers: bool = True
    verifier_provider: str = "composite"

    # --- pricing (USD per 1M tokens) --------------------------------------
    price_input_per_mtok: float = 0.30
    price_output_per_mtok: float = 2.50
    price_embedding_per_mtok: float = 0.15

    cors_origins: str = "http://localhost:5173,http://localhost:8080"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
