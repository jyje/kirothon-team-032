"""Pick a provider by name, or the first configured one."""

from __future__ import annotations

import os

from provider_manager.base import Provider
from provider_manager.bedrock import BedrockProvider
from provider_manager.codex import CodexProvider
from provider_manager.config import load_env
from provider_manager.openai_api import OpenAIProvider

PROVIDERS: dict[str, type[Provider]] = {
    "bedrock": BedrockProvider,
    "openai": OpenAIProvider,
    "codex": CodexProvider,
}


def get_provider(name: str | None = None) -> Provider:
    load_env()
    name = (name or os.getenv("PROVIDER") or "").strip().lower()
    if name:
        if name not in PROVIDERS:
            raise ValueError(f"PROVIDER must be one of {tuple(PROVIDERS)}, got {name!r}")
        return PROVIDERS[name]()
    for cls in PROVIDERS.values():
        p = cls()
        if p.is_configured():
            return p
    raise RuntimeError("No provider configured. See .env.example")
