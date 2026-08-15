"""Environment-driven configuration (Key Vault style secrets resolution)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(name: str, default: str | None = None) -> str | None:
    return os.getenv(name, default)


@dataclass(frozen=True)
class Settings:
    openai_api_key: str | None = field(default_factory=lambda: _env("OPENAI_API_KEY"))
    chat_model: str = field(default_factory=lambda: _env("CHAT_MODEL", "gpt-4o-mini"))

    azure_devops_org: str | None = field(default_factory=lambda: _env("AZURE_DEVOPS_ORG"))
    azure_devops_project: str | None = field(default_factory=lambda: _env("AZURE_DEVOPS_PROJECT"))
    azure_devops_pat: str | None = field(default_factory=lambda: _env("AZURE_DEVOPS_PAT"))

    max_retries: int = field(default_factory=lambda: int(_env("MAX_RETRIES", "3")))
    request_timeout_s: float = field(default_factory=lambda: float(_env("REQUEST_TIMEOUT_S", "15")))
    mttr_target_minutes: int = field(default_factory=lambda: int(_env("MTTR_TARGET_MINUTES", "30")))

    environment: str = field(default_factory=lambda: _env("ENVIRONMENT", "dev"))


settings = Settings()
