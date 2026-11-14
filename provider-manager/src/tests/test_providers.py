import json
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from provider_manager.bedrock import BedrockProvider
from provider_manager.codex import CodexProvider
from provider_manager.config import mask
from provider_manager.openai_api import OpenAIProvider
from provider_manager.registry import get_provider


def test_mask():
    assert mask(None) == "<unset>"
    assert mask("short") == "****"
    assert mask("abcdefghijklmnop") == "****mnop"


def test_bedrock_converse(monkeypatch):
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "secret-token-1234567890")
    client = MagicMock()
    client.converse.return_value = {"output": {"message": {"content": [{"text": "hi"}]}}}
    with patch("provider_manager.bedrock.boto3.client", return_value=client) as mk:
        p = BedrockProvider()
        assert p.complete("yo") == "hi"
    assert mk.call_args.args[0] == "bedrock-runtime"
    assert "secret-token" not in p.describe()


def test_bedrock_missing_token(monkeypatch):
    monkeypatch.delenv("AWS_BEARER_TOKEN_BEDROCK", raising=False)
    with pytest.raises(RuntimeError):
        BedrockProvider().complete("x")


def _bedrock_client(blocks):
    client = MagicMock()
    client.converse.return_value = {"output": {"message": {"content": blocks}}}
    return client


def test_bedrock_region_and_model_from_env(monkeypatch):
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "secret-token-1234567890")
    monkeypatch.setenv("AWS_REGION", "ap-northeast-2")
    monkeypatch.setenv("BEDROCK_MODEL_ID", "my.model-v1:0")
    client = _bedrock_client([{"text": "ok"}])
    with patch("provider_manager.bedrock.boto3.client", return_value=client) as mk:
        p = BedrockProvider()
        p.complete("ping")
    assert mk.call_args.kwargs["region_name"] == "ap-northeast-2"
    client.converse.assert_called_once_with(
        modelId="my.model-v1:0",
        messages=[{"role": "user", "content": [{"text": "ping"}]}],
    )


def test_bedrock_default_region(monkeypatch):
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)
    monkeypatch.delenv("BEDROCK_MODEL_ID", raising=False)
    p = BedrockProvider()
    assert p.region == "us-east-1"
    assert p.model


def test_bedrock_joins_text_blocks_and_skips_others(monkeypatch):
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "secret-token-1234567890")
    client = _bedrock_client([{"text": "a"}, {"toolUse": {}}, {"text": "b"}])
    with patch("provider_manager.bedrock.boto3.client", return_value=client):
        assert BedrockProvider().complete("x") == "ab"


def test_bedrock_is_configured(monkeypatch):
    monkeypatch.delenv("AWS_BEARER_TOKEN_BEDROCK", raising=False)
    assert not BedrockProvider().is_configured()
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "secret-token-1234567890")
    assert BedrockProvider().is_configured()


def test_bedrock_api_error_propagates(monkeypatch):
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "secret-token-1234567890")
    client = MagicMock()
    client.converse.side_effect = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "denied"}}, "Converse"
    )
    with patch("provider_manager.bedrock.boto3.client", return_value=client):
        with pytest.raises(ClientError):
            BedrockProvider().complete("x")


def test_bedrock_via_registry(monkeypatch):
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "secret-token-1234567890")
    assert isinstance(get_provider("bedrock"), BedrockProvider)


def test_openai_complete(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-real-key-1234567890")
    client = MagicMock()
    client.chat.completions.create.return_value.choices = [MagicMock()]
    client.chat.completions.create.return_value.choices[0].message.content = "hello"
    with patch("provider_manager.openai_api.OpenAI", return_value=client):
        p = OpenAIProvider()
        assert p.complete("yo") == "hello"
    assert "sk-real-key" not in p.describe()


def test_codex_status(monkeypatch, tmp_path):
    f = tmp_path / "auth.json"
    monkeypatch.setenv("CODEX_AUTH_FILE", str(f))
    assert not CodexProvider().is_configured()
    f.write_text(json.dumps({"tokens": {"access_token": "x"}}))
    p = CodexProvider()
    assert p.is_configured()
    assert "access_token" not in p.describe()


def test_registry_unknown():
    with pytest.raises(ValueError):
        get_provider("nope")
