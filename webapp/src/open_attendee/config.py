"""환경 변수에서 설정을 읽고, 필수 값이 빠졌으면 시작을 거부한다.

시크릿(`OWNER_PASSWORD_HASH`, `SESSION_SECRET`)은 `Secret`으로 감싸서 `repr`, `str`, 로그에
값이 나오지 않게 한다. 값이 필요한 곳은 `Secret.reveal()`을 명시적으로 부른다.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

REQUIRED_VARS = ("OWNER_PASSWORD_HASH", "SESSION_SECRET")
BLOB_BACKENDS = ("local", "s3")
TRANSCRIBERS = ("none", "fake", "faster_whisper", "remote")
JOURNAL_MODES = ("wal", "delete")

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off", ""}


class ConfigError(RuntimeError):
    """설정이 잘못되어 시작할 수 없다. 값은 담지 않고 변수 이름만 담는다."""

    def __init__(self, missing: tuple[str, ...] = (), invalid: tuple[str, ...] = ()) -> None:
        self.missing = missing
        self.invalid = invalid
        parts = []
        if missing:
            parts.append("필수 환경 변수가 없습니다: " + ", ".join(missing))
        if invalid:
            parts.append("값이 올바르지 않은 환경 변수: " + ", ".join(invalid))
        super().__init__("; ".join(parts))


class Secret:
    """값을 `repr`, `str`, 로그에 드러내지 않는 문자열 래퍼."""

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        self._value = value

    def reveal(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return "Secret('****')"

    __str__ = __repr__

    def __bool__(self) -> bool:
        return bool(self._value)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Secret) and self._value == other._value

    def __hash__(self) -> int:
        return hash(self._value)


@dataclass(frozen=True)
class Settings:
    owner_password_hash: Secret
    session_secret: Secret
    data_dir: Path = Path("./data")
    blob_backend: str = "local"
    s3_bucket: str | None = None
    feature_recording: bool = False
    transcriber: str = "none"
    stt_model: str = "small"
    provider: str | None = None
    sqlite_journal_mode: str = "wal"  # NFS 볼륨에서는 "delete"

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        """환경 변수로 설정을 만든다.

        `environ`을 주지 않으면 `provider_manager.config.load_env()`로 `.env`를 읽은 뒤
        `os.environ`을 쓴다. 테스트는 `environ`을 직접 넘겨서 `.env`를 읽지 않는다.
        """
        if environ is None:
            from provider_manager.config import load_env

            load_env()
            environ = os.environ

        def get(name: str, default: str | None = None) -> str | None:
            value = environ.get(name)
            if value is None or not value.strip():
                return default
            return value.strip()

        missing = tuple(name for name in REQUIRED_VARS if get(name) is None)
        invalid: list[str] = []

        blob_backend = (get("BLOB_BACKEND", "local") or "local").lower()
        if blob_backend not in BLOB_BACKENDS:
            invalid.append("BLOB_BACKEND")
        s3_bucket = get("S3_BUCKET")
        if blob_backend == "s3" and s3_bucket is None:
            missing = (*missing, "S3_BUCKET")

        transcriber = (get("TRANSCRIBER", "none") or "none").lower()
        if transcriber not in TRANSCRIBERS:
            invalid.append("TRANSCRIBER")

        journal_mode = (get("SQLITE_JOURNAL_MODE", "wal") or "wal").lower()
        if journal_mode not in JOURNAL_MODES:
            invalid.append("SQLITE_JOURNAL_MODE")
        recording_raw = (environ.get("FEATURE_RECORDING") or "").strip().lower()
        if recording_raw in _TRUE:
            feature_recording = True
        elif recording_raw in _FALSE:
            feature_recording = False
        else:
            feature_recording = False
            invalid.append("FEATURE_RECORDING")

        if missing or invalid:
            raise ConfigError(missing=missing, invalid=tuple(invalid))

        provider = get("PROVIDER")
        return cls(
            owner_password_hash=Secret(get("OWNER_PASSWORD_HASH") or ""),
            session_secret=Secret(get("SESSION_SECRET") or ""),
            data_dir=Path(get("DATA_DIR", "./data") or "./data"),
            blob_backend=blob_backend,
            s3_bucket=s3_bucket,
            feature_recording=feature_recording,
            transcriber=transcriber,
            stt_model=get("STT_MODEL", "small") or "small",
            provider=provider.lower() if provider else None,
            sqlite_journal_mode=journal_mode,
        )

    @property
    def db_path(self) -> Path:
        return self.data_dir / "open_attendee.sqlite3"
