"""Load .env once and mask secrets for logs."""

from __future__ import annotations

import functools
import os

from dotenv import find_dotenv, load_dotenv

# Values copied from .env.example. A variable holding one of them is not really set.
PLACEHOLDERS = ("your-", "sk-your-")


@functools.cache
def load_env() -> None:
    load_dotenv(find_dotenv())


def env_is_set(name: str) -> bool:
    value = os.getenv(name, "")
    return bool(value) and not value.startswith(PLACEHOLDERS)


def codex_enabled() -> bool:
    """Codex is optional: on with CODEX_ENABLED=true, or when PROVIDER=codex."""
    load_env()
    on = os.getenv("CODEX_ENABLED", "").strip().lower() in ("1", "true", "yes", "on")
    return on or os.getenv("PROVIDER", "").strip().lower() == "codex"


def mask(secret: str | None) -> str:
    """Show at most the last 4 characters, and nothing for short secrets."""
    if not secret:
        return "<unset>"
    return "****" + secret[-4:] if len(secret) > 12 else "****"
