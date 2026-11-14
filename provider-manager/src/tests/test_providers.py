import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest
from strands import Agent
from strands.models import BedrockModel
from strands.models.openai import OpenAIModel

from provider_manager import factory
from provider_manager.__main__ import main
from provider_manager.codex import CodexError, CodexModel, auth_path
from provider_manager.config import codex_enabled, mask

KEY = "sk-real-key-1234567890"
TOKEN = "secret-token-1234567890"


@pytest.fixture(autouse=True)
def clean(monkeypatch, tmp_path):
    for v in ("PROVIDER", "OPENAI_MODEL", "BEDROCK_MODEL_ID", "AWS_REGION", "AWS_DEFAULT_REGION",
              "CODEX_BIN", "CODEX_MODEL", "CODEX_TIMEOUT",
              "CODEX_ENABLED", "CODEX_HOME"):  # fmt: skip
        monkeypatch.delenv(v, raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AWS_BEARER_TOKEN_BEDROCK", raising=False)
    monkeypatch.setenv("CODEX_AUTH_FILE", str(tmp_path / "auth.json"))


def sign_in(tmp_path):
    (tmp_path / "auth.json").write_text(json.dumps({"tokens": {"access_token": "x"}}))


def test_mask():
    assert mask(None) == "<unset>"
    assert mask("short") == "****"
    assert mask("abcdefghijklmnop") == "****mnop"


def test_default_provider_is_openai():
    assert factory.resolve() == "openai"


def test_env_provider(monkeypatch):
    monkeypatch.setenv("PROVIDER", "Bedrock")
    assert factory.resolve() == "bedrock"
    assert factory.resolve("codex") == "codex"


def test_unknown_provider():
    with pytest.raises(ValueError):
        factory.resolve("nope")


def test_openai_model(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", KEY)
    monkeypatch.setenv("OPENAI_MODEL", "gpt-x")
    m = factory.build_model("openai")
    assert isinstance(m, OpenAIModel)
    assert m.get_config()["model_id"] == "gpt-x"
    assert "sk-real-key" not in factory.describe("openai")


def test_bedrock_model(monkeypatch):
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", TOKEN)
    monkeypatch.setenv("AWS_REGION", "ap-northeast-2")
    monkeypatch.setenv("BEDROCK_MODEL_ID", "my.model-v1:0")
    m = factory.build_model("bedrock")
    assert isinstance(m, BedrockModel)
    assert m.get_config()["model_id"] == "my.model-v1:0"
    assert m.client.meta.region_name == "ap-northeast-2"
    assert "secret-token" not in factory.describe("bedrock")


def test_bedrock_default_region():
    assert "region=us-east-1" in factory.describe("bedrock")


@pytest.mark.parametrize("name", ["openai", "bedrock"])
def test_missing_config(name):
    assert not factory.is_configured(name)
    with pytest.raises(RuntimeError, match="is not set"):
        factory.build_model(name)


def test_placeholder_is_not_configured(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-your-openai-key")
    assert not factory.is_configured("openai")


def test_codex_factory(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_ENABLED", "true")
    with patch("provider_manager.factory.shutil.which", return_value="/bin/codex"):
        assert isinstance(factory.build_model("codex"), CodexModel)
    assert not factory.is_configured("codex")
    sign_in(tmp_path)
    assert factory.is_configured("codex")
    assert "access_token" not in factory.describe("codex")


def _run(returncode=0, stdout="hi\n", stderr=""):
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


def test_codex_agent_call(tmp_path):
    sign_in(tmp_path)
    with (
        patch("provider_manager.codex.shutil.which", return_value="/bin/codex"),
        patch("provider_manager.codex.subprocess.run", return_value=_run()) as run,
    ):
        out = Agent(model=CodexModel(model_id="m1"), callback_handler=None)("yo")
    assert str(out).strip() == "hi"
    args = run.call_args.args[0]
    assert args[:2] == ["/bin/codex", "exec"]
    assert args[-1] == "-"
    assert args[args.index("-m") + 1] == "m1"
    assert run.call_args.kwargs["input"] == "yo"
    assert run.call_args.kwargs["timeout"] == 120.0


def test_codex_not_installed():
    with patch("provider_manager.codex.shutil.which", return_value=None):
        with pytest.raises(CodexError, match="not found"):
            CodexModel().run("x")


def test_codex_not_signed_in():
    with patch("provider_manager.codex.shutil.which", return_value="/bin/codex"):
        with pytest.raises(CodexError, match="codex login"):
            CodexModel().run("x")


def test_codex_timeout_and_failure(tmp_path):
    sign_in(tmp_path)
    with patch("provider_manager.codex.shutil.which", return_value="/bin/codex"):
        with patch(
            "provider_manager.codex.subprocess.run",
            side_effect=subprocess.TimeoutExpired("codex", 1),
        ):
            with pytest.raises(CodexError, match="timed out"):
                CodexModel(timeout=1).run("x")
        with patch("provider_manager.codex.subprocess.run", return_value=_run(2, "", "boom")):
            with pytest.raises(CodexError, match="boom"):
                CodexModel().run("x")


def test_ask_uses_one_agent_path(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", KEY)
    fake = MagicMock(return_value="  hello ")
    with patch("provider_manager.factory.Agent", return_value=fake) as agent:
        assert factory.ask("yo") == "hello"
    assert isinstance(agent.call_args.kwargs["model"], OpenAIModel)


def test_cli_status_masks(monkeypatch, capsys):
    monkeypatch.setenv("OPENAI_API_KEY", KEY)
    assert main(["status"]) == 0
    out = capsys.readouterr().out
    assert "active: openai" in out
    assert KEY not in out


def test_cli_ask_missing_config(capsys):
    assert main(["ask", "--provider", "openai", "hi"]) == 1
    assert "OPENAI_API_KEY" in capsys.readouterr().err


def test_codex_disabled_by_default(capsys):
    assert "disabled" in factory.describe("codex")
    assert not factory.is_configured("codex")
    with pytest.raises(RuntimeError, match="CODEX_ENABLED=true"):
        factory.build_model("codex")
    assert main(["status"]) == 0
    out = capsys.readouterr().out
    assert "off " in out
    assert "codex disabled" in out


def test_provider_codex_implies_enabled(monkeypatch):
    monkeypatch.setenv("PROVIDER", "codex")
    assert codex_enabled()
    with patch("provider_manager.factory.shutil.which", return_value=None):
        with pytest.raises(RuntimeError, match="not installed"):
            factory.build_model()


def test_codex_home_sets_auth_path(monkeypatch, tmp_path):
    monkeypatch.delenv("CODEX_AUTH_FILE")
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    assert auth_path() == tmp_path / "auth.json"
