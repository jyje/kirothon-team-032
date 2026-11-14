"""OpenAI API key provider."""

from __future__ import annotations

import os

from openai import OpenAI

from provider_manager.base import Provider
from provider_manager.config import env_is_set, load_env, mask

DEFAULT_MODEL = "gpt-4o-mini"


class OpenAIProvider(Provider):
    name = "openai"

    def __init__(self) -> None:
        load_env()
        self.model = os.getenv("OPENAI_MODEL") or DEFAULT_MODEL

    def is_configured(self) -> bool:
        return env_is_set("OPENAI_API_KEY")

    def describe(self) -> str:
        return f"openai model={self.model} key={mask(os.getenv('OPENAI_API_KEY'))}"

    def complete(self, prompt: str) -> str:
        if not self.is_configured():
            raise RuntimeError("OPENAI_API_KEY is not set")
        client = OpenAI()
        resp = client.chat.completions.create(
            model=self.model, messages=[{"role": "user", "content": prompt}]
        )
        return resp.choices[0].message.content or ""
