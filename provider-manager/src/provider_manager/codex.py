"""Strands model that calls OpenAI Codex through the Codex CLI (`codex exec`).

It uses the ChatGPT sign-in made by `codex login`. No token is read or sent by this code: the
CLI owns the credentials. Text in, text out. shortcut: no tool calls, no streaming and no
structured output, because `codex exec` is an agent CLI, not a chat API; upgrade if needed.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from strands.models import Model

from provider_manager.config import load_env

DEFAULT_TIMEOUT = 120.0


class CodexError(RuntimeError):
    """Codex CLI missing, not signed in, timed out, or failed."""


def auth_path() -> Path:
    load_env()
    home = os.getenv("CODEX_HOME") or "~/.codex"
    return Path(os.getenv("CODEX_AUTH_FILE") or f"{home}/auth.json").expanduser()


def signed_in() -> bool:
    """Check the token file by structure only. The token value is never read out."""
    try:
        data = json.loads(auth_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(data, dict) and bool(data.get("tokens") or data.get("OPENAI_API_KEY"))


def _text(messages: list[Any]) -> str:
    lines = []
    for m in messages:
        text = "".join(b.get("text", "") for b in m["content"])
        lines.append(f"{m['role']}: {text}" if len(messages) > 1 else text)
    return "\n".join(lines)


class CodexModel(Model):
    def __init__(
        self,
        *,
        binary: str | None = None,
        model_id: str | None = None,
        timeout: float | None = None,
    ) -> None:
        load_env()
        self.config: dict[str, Any] = {
            "binary": binary or os.getenv("CODEX_BIN") or "codex",
            "model_id": model_id or os.getenv("CODEX_MODEL") or None,
            "timeout": timeout or float(os.getenv("CODEX_TIMEOUT") or DEFAULT_TIMEOUT),
        }

    def update_config(self, **model_config: Any) -> None:
        self.config.update(model_config)

    def get_config(self) -> dict[str, Any]:
        return self.config

    def run(self, prompt: str) -> str:
        binary = shutil.which(self.config["binary"])
        if not binary:
            raise CodexError(f"Codex CLI not found: {self.config['binary']!r}. Install it first.")
        if not signed_in():
            raise CodexError("Codex is not signed in. Run: codex login")
        cmd = [binary, "exec", "--skip-git-repo-check", "--ephemeral", "-s", "read-only"]
        if self.config["model_id"]:
            cmd += ["-m", self.config["model_id"]]
        try:
            # prompt goes through stdin: no shell, no argv length limit
            r = subprocess.run(
                [*cmd, "-"],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=self.config["timeout"],
                check=False,
            )
        except subprocess.TimeoutExpired as e:
            raise CodexError(f"codex exec timed out after {self.config['timeout']}s") from e
        if r.returncode != 0:
            raise CodexError(f"codex exec failed ({r.returncode}): {r.stderr.strip()[-500:]}")
        return r.stdout.strip()

    async def stream(  # type: ignore[override]
        self, messages: Any, tool_specs: Any = None, system_prompt: str | None = None, **kwargs: Any
    ) -> AsyncGenerator[Any]:
        prompt = _text(messages)
        if system_prompt:
            prompt = f"{system_prompt}\n\n{prompt}"
        text = await asyncio.to_thread(self.run, prompt)
        yield {"messageStart": {"role": "assistant"}}
        yield {"contentBlockStart": {"start": {}}}
        yield {"contentBlockDelta": {"delta": {"text": text}}}
        yield {"contentBlockStop": {}}
        yield {"messageStop": {"stopReason": "end_turn"}}

    async def structured_output(  # type: ignore[override]
        self, output_model: Any, prompt: Any, system_prompt: str | None = None, **kwargs: Any
    ) -> AsyncGenerator[Any]:
        raise NotImplementedError("CodexModel does not support structured output")
        yield  # pragma: no cover
