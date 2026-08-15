"""
Centralized, environment-driven configuration.

Mirrors an Azure Key Vault style secrets pattern: nothing sensitive is
hardcoded, everything is resolved from the environment at startup, and a
single `Settings` object is the one source of truth for the whole service.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(name: str, default: str | None = None, required: bool = False) -> str | None:
    value = os.getenv(name, default)
    if required and not value:
        raise RuntimeError(
            f"Missing required environment variable '{name}'. "
            "In production this is resolved from a secrets manager "
            "(e.g. Azure Key Vault) rather than a plain .env file."
        )
    return value


@dataclass(frozen=True)
class Settings:
    openai_api_key: str | None = field(default_factory=lambda: _env("OPENAI_API_KEY"))
    chat_model: str = field(default_factory=lambda: _env("CHAT_MODEL", "gpt-4o-mini"))
    embedding_model: str = field(
        default_factory=lambda: _env("EMBEDDING_MODEL", "text-embedding-3-small")
    )

    vector_store_path: str = field(
        default_factory=lambda: _env("VECTOR_STORE_PATH", "./data/index")
    )
    raw_docs_path: str = field(default_factory=lambda: _env("RAW_DOCS_PATH", "./data/bronze"))
    silver_docs_path: str = field(
        default_factory=lambda: _env("SILVER_DOCS_PATH", "./data/silver")
    )

    chunk_size: int = field(default_factory=lambda: int(_env("CHUNK_SIZE", "800")))
    chunk_overlap: int = field(default_factory=lambda: int(_env("CHUNK_OVERLAP", "120")))
    top_k: int = field(default_factory=lambda: int(_env("TOP_K", "5")))

    max_retries: int = field(default_factory=lambda: int(_env("MAX_RETRIES", "3")))
    request_timeout_s: float = field(
        default_factory=lambda: float(_env("REQUEST_TIMEOUT_S", "30"))
    )
    sla_latency_ms: int = field(default_factory=lambda: int(_env("SLA_LATENCY_MS", "4000")))

    environment: str = field(default_factory=lambda: _env("ENVIRONMENT", "dev"))


settings = Settings()
