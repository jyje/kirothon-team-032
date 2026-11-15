"""설정 읽기와 시작 검사 (요구사항 26.1, 26.2, 11.1, 12.4, 12.5)."""

from __future__ import annotations

from pathlib import Path

import pytest

from open_attendee.config import ConfigError, Secret, Settings

from .conftest import OWNER_HASH, SESSION_SECRET


def test_defaults(env: dict[str, str]) -> None:
    s = Settings.from_env({k: v for k, v in env.items() if k != "DATA_DIR"})
    assert s.feature_recording is False  # 11.1
    assert s.transcriber == "none"
    assert s.stt_model == "small"  # 12.5
    assert s.blob_backend == "local"
    assert s.data_dir == Path("./data")
    assert s.s3_bucket is None
    assert s.provider is None


def test_values_are_read(env: dict[str, str]) -> None:
    env.update(
        FEATURE_RECORDING="true",
        TRANSCRIBER="faster_whisper",
        STT_MODEL="medium",
        BLOB_BACKEND="s3",
        S3_BUCKET="my-bucket",
        AWS_REGION="us-east-1",
        S3_ENDPOINT_URL="http://127.0.0.1:9000",
        PROVIDER="Bedrock",
    )
    s = Settings.from_env(env)
    assert s.feature_recording is True
    assert s.transcriber == "faster_whisper"
    assert s.stt_model == "medium"
    assert s.blob_backend == "s3"
    assert s.s3_bucket == "my-bucket"
    assert s.s3_region == "us-east-1"
    assert s.s3_endpoint == "http://127.0.0.1:9000"
    assert s.provider == "bedrock"
    assert s.owner_password_hash.reveal() == OWNER_HASH
    assert s.session_secret.reveal() == SESSION_SECRET


@pytest.mark.parametrize("missing", ["OWNER_PASSWORD_HASH", "SESSION_SECRET"])
def test_missing_required_variable_refuses_start(env: dict[str, str], missing: str) -> None:
    del env[missing]
    with pytest.raises(ConfigError) as exc:
        Settings.from_env(env)
    assert exc.value.missing == (missing,)
    assert missing in str(exc.value)  # 26.2: 빠진 변수 이름을 알린다.


def test_blank_required_variable_counts_as_missing(env: dict[str, str]) -> None:
    env["SESSION_SECRET"] = "   "
    with pytest.raises(ConfigError) as exc:
        Settings.from_env(env)
    assert exc.value.missing == ("SESSION_SECRET",)


def test_all_missing_variables_are_reported_together() -> None:
    with pytest.raises(ConfigError) as exc:
        Settings.from_env({})
    assert set(exc.value.missing) == {"OWNER_PASSWORD_HASH", "SESSION_SECRET"}


def test_s3_backend_requires_bucket(env: dict[str, str]) -> None:
    env["BLOB_BACKEND"] = "s3"
    with pytest.raises(ConfigError) as exc:
        Settings.from_env(env)
    assert exc.value.missing == ("S3_BUCKET",)


@pytest.mark.parametrize(
    ("name", "value"),
    [("BLOB_BACKEND", "ftp"), ("TRANSCRIBER", "magic"), ("FEATURE_RECORDING", "maybe")],
)
def test_invalid_value_names_the_variable_not_the_value(
    env: dict[str, str], name: str, value: str
) -> None:
    env[name] = value
    with pytest.raises(ConfigError) as exc:
        Settings.from_env(env)
    assert exc.value.invalid == (name,)
    assert value not in str(exc.value)


def test_secrets_do_not_appear_in_repr_str_or_format(settings: Settings) -> None:
    for text in (repr(settings), str(settings), f"{settings}", repr(settings.session_secret)):
        assert SESSION_SECRET not in text
        assert OWNER_HASH not in text
    assert str(settings.owner_password_hash) == "Secret('****')"


def test_secret_equality_and_truthiness() -> None:
    assert Secret("a") == Secret("a")
    assert Secret("a") != Secret("b")
    assert not Secret("")


def test_sqlite_journal_mode_defaults_to_wal_and_validates(env: dict[str, str]) -> None:
    from open_attendee.config import ConfigError

    assert Settings.from_env(env).sqlite_journal_mode == "wal"
    assert (
        Settings.from_env({**env, "SQLITE_JOURNAL_MODE": "DELETE"}).sqlite_journal_mode == "delete"
    )
    with pytest.raises(ConfigError) as err:
        Settings.from_env({**env, "SQLITE_JOURNAL_MODE": "memory"})
    assert "SQLITE_JOURNAL_MODE" in str(err.value)
