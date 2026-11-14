"""`/healthz`와 앱 조립 (요구사항 26.3, 26.4)."""

from __future__ import annotations

import logging

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from provider_manager.base import Provider

from open_attendee.config import Settings
from open_attendee.logging_redact import Sensitive
from open_attendee.main import create_app, discover_routers

from .conftest import OWNER_HASH, SESSION_SECRET

API_KEY = "sk-live-0123456789abcdef"


class StubProvider(Provider):
    """키가 설정된 Bedrock 제공자 흉내. `describe()`는 일부러 키 끝자리를 담는다."""

    name = "bedrock"
    region = "us-east-1"

    def is_configured(self) -> bool:
        return True

    def describe(self) -> str:
        return f"bedrock region={self.region} token=****{API_KEY[-4:]}"

    def complete(self, prompt: str) -> str:
        raise AssertionError("healthz는 LLM을 부르지 않는다")


def test_healthz_without_llm(client: TestClient) -> None:
    res = client.get("/healthz")
    assert res.status_code == 200
    body = res.json()
    assert body["ready"] is True
    assert body["llm"] == {"configured": False, "provider": None, "region": None}
    assert body["storage"]["backend"] == "local"
    assert body["storage"]["free_bytes"] > 0


def test_healthz_needs_no_login(client: TestClient) -> None:
    assert client.get("/healthz").status_code == 200


def test_healthz_reports_provider_and_region_without_secrets(settings: Settings) -> None:
    app = create_app(settings, provider_factory=lambda: StubProvider())
    with TestClient(app) as client:
        res = client.get("/healthz")
    assert res.json()["llm"] == {"configured": True, "provider": "bedrock", "region": "us-east-1"}
    for secret in (OWNER_HASH, SESSION_SECRET, API_KEY, API_KEY[-4:]):
        assert secret not in res.text


def test_healthz_is_503_when_database_is_unavailable(settings: Settings) -> None:
    app = create_app(settings, provider_factory=lambda: None)
    with TestClient(app) as client:
        client.app.state.engine.dispose()  # type: ignore[attr-defined]
        client.app.state.engine = None  # type: ignore[attr-defined]
        res = client.get("/healthz")
    assert res.status_code == 503
    assert res.json()["ready"] is False


def test_docs_endpoints_are_off(client: TestClient) -> None:
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404


def test_database_file_is_created_in_data_dir(client: TestClient, settings: Settings) -> None:
    assert settings.db_path.exists()


def test_routes_modules_are_registered_automatically() -> None:
    routers = discover_routers()
    assert all(isinstance(r, APIRouter) for r in routers)


def test_validation_error_does_not_echo_input(settings: Settings) -> None:
    app = create_app(settings, provider_factory=lambda: None)
    router = APIRouter()

    @router.post("/echo-test")
    def echo(count: int) -> dict[str, int]:
        return {"count": count}

    app.include_router(router)
    with TestClient(app) as client:
        res = client.post("/echo-test", params={"count": "my-private-note"})
    assert res.status_code == 422
    assert "my-private-note" not in res.text


def test_unhandled_error_hides_message(settings: Settings) -> None:
    app = create_app(settings, provider_factory=lambda: None)
    router = APIRouter()

    @router.get("/boom-test")
    def boom() -> None:
        raise RuntimeError(f"프롬프트 원문 {API_KEY}")

    app.include_router(router)
    with TestClient(app, raise_server_exceptions=False) as client:
        res = client.get("/boom-test")
    assert res.status_code == 500
    assert API_KEY not in res.text
    assert "프롬프트" not in res.text


def test_logs_mask_registered_secrets_and_sensitive_values(
    settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    create_app(settings, provider_factory=lambda: None)
    log = logging.getLogger("open_attendee.test")
    with caplog.at_level(logging.INFO, logger="open_attendee.test"):
        log.info("세션 서명 키 %s", SESSION_SECRET)
        log.info("해시 %s", OWNER_HASH)
        log.info("헤더 Authorization: Bearer abc.def-123")
        log.info("프롬프트 %s", Sensitive("회의에서 들은 비밀 내용"))
        log.error("작업 실패", exc_info=RuntimeError(f"실패 {SESSION_SECRET}"))
    text = caplog.text
    assert SESSION_SECRET not in text
    assert OWNER_HASH not in text
    assert "abc.def-123" not in text
    assert "비밀 내용" not in text
    assert "<redacted" in text
