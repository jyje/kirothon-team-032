"""공용 pytest 픽스처.

테스트는 `.env`를 읽지 않는다. 설정은 `Settings.from_env(dict)`로 직접 만들고,
LLM 제공자는 `provider_factory`로 주입한다.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from open_attendee.config import Settings
from open_attendee.db import init_db, make_engine
from open_attendee.main import create_app

OWNER_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdHNhbHQ$aGFzaGhhc2hoYXNo"
SESSION_SECRET = "test-session-secret-value"


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    return {
        "OWNER_PASSWORD_HASH": OWNER_HASH,
        "SESSION_SECRET": SESSION_SECRET,
        "DATA_DIR": str(tmp_path / "data"),
    }


@pytest.fixture
def settings(env: dict[str, str]) -> Settings:
    return Settings.from_env(env)


@pytest.fixture
def engine(settings: Settings) -> Iterator[Engine]:
    engine = make_engine(settings.db_path)
    init_db(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings, provider_factory=lambda: None)
    with TestClient(app) as test_client:
        yield test_client
