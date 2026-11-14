"""AWS Bedrock through the Converse API, authenticated by a Bedrock API key (bearer token).

boto3 reads AWS_BEARER_TOKEN_BEDROCK itself (boto3 >= 1.39), so no SigV4 credentials are needed.
"""

from __future__ import annotations

import os

import boto3

from provider_manager.base import Provider
from provider_manager.config import env_is_set, load_env, mask

DEFAULT_MODEL = "us.anthropic.claude-3-5-haiku-20241022-v1:0"


class BedrockProvider(Provider):
    name = "bedrock"

    def __init__(self) -> None:
        load_env()
        self.region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-east-1"
        self.model = os.getenv("BEDROCK_MODEL_ID") or DEFAULT_MODEL

    def is_configured(self) -> bool:
        return env_is_set("AWS_BEARER_TOKEN_BEDROCK")

    def describe(self) -> str:
        token = mask(os.getenv("AWS_BEARER_TOKEN_BEDROCK"))
        return f"bedrock region={self.region} model={self.model} token={token}"

    def complete(self, prompt: str) -> str:
        if not self.is_configured():
            raise RuntimeError("AWS_BEARER_TOKEN_BEDROCK is not set")
        client = boto3.client("bedrock-runtime", region_name=self.region)
        resp = client.converse(
            modelId=self.model,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
        )
        return "".join(b.get("text", "") for b in resp["output"]["message"]["content"])
