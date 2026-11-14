"""One factory: provider name -> Strands model. One Agent path for every provider."""

from __future__ import annotations

import os
import shutil

from strands import Agent
from strands.models import Model

from provider_manager.codex import CodexModel, auth_path, signed_in
from provider_manager.config import codex_enabled, env_is_set, load_env, mask

PROVIDERS = ("bedrock", "openai", "codex")
DEFAULT_PROVIDER = "openai"
BEDROCK_MODEL = "us.anthropic.claude-3-5-haiku-20241022-v1:0"
OPENAI_MODEL = "gpt-4o-mini"


def resolve(name: str | None = None) -> str:
    load_env()
    name = (name or os.getenv("PROVIDER") or DEFAULT_PROVIDER).strip().lower()
    if name not in PROVIDERS:
        raise ValueError(f"PROVIDER must be one of {PROVIDERS}, got {name!r}")
    return name


def _region() -> str:
    return os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-east-1"


def is_configured(name: str) -> bool:
    load_env()
    if name == "bedrock":
        return env_is_set("AWS_BEARER_TOKEN_BEDROCK")
    if name == "openai":
        return env_is_set("OPENAI_API_KEY")
    return codex_enabled() and signed_in()


CODEX_HOWTO = "set CODEX_ENABLED=true (or PROVIDER=codex), then run: codex login"


def describe(name: str) -> str:
    """One safe line: secrets are masked."""
    load_env()
    if name == "bedrock":
        model = os.getenv("BEDROCK_MODEL_ID") or BEDROCK_MODEL
        token = mask(os.getenv("AWS_BEARER_TOKEN_BEDROCK"))
        return f"bedrock region={_region()} model={model} token={token}"
    if name == "openai":
        model = os.getenv("OPENAI_MODEL") or OPENAI_MODEL
        return f"openai model={model} key={mask(os.getenv('OPENAI_API_KEY'))}"
    if not codex_enabled():
        return "codex disabled (optional: set CODEX_ENABLED=true to use it)"
    state = "signed in" if signed_in() else "not signed in (run: codex login)"
    return f"codex auth_file={auth_path()} {state}"


def build_model(name: str | None = None) -> Model:
    name = resolve(name)
    if name == "codex":
        binary = os.getenv("CODEX_BIN") or "codex"
        if not codex_enabled():
            raise RuntimeError(f"Codex is disabled. To enable it: {CODEX_HOWTO}")
        if not shutil.which(binary):
            raise RuntimeError(
                f"Codex CLI {binary!r} is not installed. Install: npm i -g @openai/codex "
                "(the container does it when CODEX_ENABLED=true)"
            )
    elif not is_configured(name):
        var = "AWS_BEARER_TOKEN_BEDROCK" if name == "bedrock" else "OPENAI_API_KEY"
        raise RuntimeError(f"{var} is not set. See .env.example")
    if name == "bedrock":
        from strands.models import BedrockModel

        # boto3 reads AWS_BEARER_TOKEN_BEDROCK itself
        return BedrockModel(
            model_id=os.getenv("BEDROCK_MODEL_ID") or BEDROCK_MODEL, region_name=_region()
        )
    if name == "openai":
        from strands.models.openai import OpenAIModel

        return OpenAIModel(
            client_args={"api_key": os.environ["OPENAI_API_KEY"]},
            model_id=os.getenv("OPENAI_MODEL") or OPENAI_MODEL,
        )
    return CodexModel()


def ask(prompt: str, provider: str | None = None) -> str:
    agent = Agent(model=build_model(provider), callback_handler=None)
    return str(agent(prompt)).strip()
