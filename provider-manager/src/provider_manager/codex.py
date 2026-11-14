"""OpenAI Codex subscription (ChatGPT sign-in through the Codex CLI).

Only the sign-in is managed here: it checks the Codex CLI token file by structure and never
reads a token value into a message. shortcut: `complete` is not implemented, because the Codex
backend is not a public API; upgrade once a supported client exists.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from provider_manager.base import Provider
from provider_manager.config import load_env


class CodexProvider(Provider):
    name = "codex"

    def __init__(self) -> None:
        load_env()
        raw = os.getenv("CODEX_AUTH_FILE") or "~/.codex/auth.json"
        self.path = Path(raw).expanduser()

    def is_configured(self) -> bool:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        return isinstance(data, dict) and bool(data.get("tokens") or data.get("OPENAI_API_KEY"))

    def describe(self) -> str:
        state = "signed in" if self.is_configured() else "not signed in (run: codex login)"
        return f"codex auth_file={self.path} {state}"

    def complete(self, prompt: str) -> str:
        raise NotImplementedError("Codex subscription inference is not supported yet")
