"""공용 pytest 픽스처.

테스트는 `.env`를 읽지 않는다. 설정은 `Settings.from_env(dict)`로 직접 만들고,
LLM 제공자는 `provider_factory`로 주입한다.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlmodel import Session

from open_attendee.config import Settings
from open_attendee.db import init_db, make_engine
from open_attendee.main import create_app
from open_attendee.sessions import SessionService
from open_attendee.storage import LocalBlobStore

OWNER_PASSWORD = "correct-horse-battery"
# 테스트가 느려지지 않게 비용을 최소로 낮춘 진짜 argon2 해시.
OWNER_HASH = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash(OWNER_PASSWORD)
SESSION_SECRET = "test-session-secret-value"
# 세션 쿠키가 `Secure`라서 테스트 클라이언트도 https 주소를 쓴다.
BASE_URL = "https://testserver"
_TOKEN_RE = re.compile(r'name="csrf_token" value="([^"]+)"')


def login(client: TestClient, password: str = OWNER_PASSWORD) -> str:
    """로그인하고 이후 요청에 쓸 CSRF 토큰을 돌려준다."""
    page = client.get("/login")
    match = _TOKEN_RE.search(page.text)
    assert match, "로그인 화면에 CSRF 토큰이 없다"
    res = client.post(
        "/login", data={"password": password, "csrf_token": match.group(1)}, follow_redirects=False
    )
    assert res.status_code == 303, res.text
    return csrf_token(client)


def csrf_token(client: TestClient) -> str:
    """로그인한 클라이언트의 CSRF 토큰. 앱이 쓰는 계산과 같다."""
    from open_attendee.auth import SESSION_COOKIE

    auth = client.app.state.auth  # type: ignore[attr-defined]
    seed = auth.read_session(client.cookies.get(SESSION_COOKIE))
    assert seed, "로그인하지 않았다"
    return auth.csrf_token(seed)


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
    with TestClient(app, base_url=BASE_URL) as test_client:
        yield test_client


@pytest.fixture
def auth_client(client: TestClient) -> TestClient:
    """로그인을 마친 클라이언트. 상태를 바꾸는 요청에는 `X-CSRF-Token` 헤더가 기본으로 붙는다."""
    token = login(client)
    client.headers["X-CSRF-Token"] = token
    return client


@pytest.fixture
def blobs(settings: Settings) -> LocalBlobStore:
    return LocalBlobStore(settings.data_dir / "blobs")


@pytest.fixture
def db(engine: Engine) -> Iterator[Session]:
    with Session(engine) as session:
        yield session


@pytest.fixture
def sessions(db: Session, blobs: LocalBlobStore) -> SessionService:
    return SessionService(db, blobs)
