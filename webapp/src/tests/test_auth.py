"""인증 단위 테스트 (요구사항 25.1~25.6, 2.7)."""

from __future__ import annotations

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from open_attendee.auth import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    LoginRateLimiter,
)
from open_attendee.config import Settings
from open_attendee.main import create_app

from .conftest import BASE_URL, OWNER_HASH, OWNER_PASSWORD, SESSION_SECRET, include_first, login


def _login_token(client: TestClient) -> str:
    return client.get("/api/csrf").json()["csrf_token"]


def _post_login(client: TestClient, password: str, token: str | None = None):
    token = token if token is not None else _login_token(client)
    return client.post("/api/login", json={"password": password}, headers={"X-CSRF-Token": token})


@pytest.fixture
def app_with_routes(settings: Settings):
    """로그인 보호와 CSRF를 확인할 테스트용 경로를 더한 앱."""
    app = create_app(settings, provider_factory=lambda: None)
    router = APIRouter()

    @router.get("/probe")
    def probe() -> dict[str, bool]:
        return {"ok": True}

    @router.post("/probe")
    def probe_post() -> dict[str, bool]:
        return {"ok": True}

    include_first(app, router)
    return app


@pytest.fixture
def probe_client(app_with_routes) -> TestClient:
    with TestClient(app_with_routes, base_url=BASE_URL) as client:
        yield client


# ---------------------------------------------------------------- 로그인 (25.1, 25.2)


def test_login_succeeds_with_correct_password(client: TestClient) -> None:
    res = _post_login(client, OWNER_PASSWORD)
    assert res.status_code == 200
    assert client.cookies.get(SESSION_COOKIE)


def test_login_fails_with_wrong_password(client: TestClient) -> None:
    res = _post_login(client, "wrong-password")
    assert res.status_code == 401
    assert "비밀번호가 맞지 않아요" in res.json()["error"]["message"]
    assert SESSION_COOKIE not in client.cookies


def test_login_fails_when_configured_hash_is_not_argon2(env: dict[str, str]) -> None:
    env["OWNER_PASSWORD_HASH"] = "not-an-argon2-hash"
    app = create_app(Settings.from_env(env), provider_factory=lambda: None)
    with TestClient(app, base_url=BASE_URL) as client:
        assert _post_login(client, OWNER_PASSWORD).status_code == 401


def test_session_cookie_attributes(client: TestClient) -> None:
    res = _post_login(client, OWNER_PASSWORD)
    set_cookie = next(
        v for v in res.headers.get_list("set-cookie") if v.startswith(f"{SESSION_COOKIE}=")
    )
    lowered = set_cookie.lower()
    assert "httponly" in lowered
    assert "secure" in lowered
    assert "samesite=lax" in lowered
    assert "max-age=" in lowered


def test_anonymous_csrf_cookie_attributes(client: TestClient) -> None:
    res = client.get("/api/csrf")
    set_cookie = res.headers["set-cookie"].lower()
    assert set_cookie.startswith(f"{CSRF_COOKIE}=")
    assert "httponly" in set_cookie
    assert "secure" in set_cookie
    assert "samesite=lax" in set_cookie


def test_tampered_session_cookie_is_rejected(probe_client: TestClient) -> None:
    login(probe_client)
    cookie = probe_client.cookies.get(SESSION_COOKIE)
    probe_client.cookies.delete(SESSION_COOKIE)
    probe_client.cookies.set(SESSION_COOKIE, ("X" if cookie[0] != "X" else "Y") + cookie[1:])
    assert probe_client.get("/probe").status_code == 401


def test_session_cookie_signed_with_another_secret_is_rejected(
    env: dict[str, str], probe_client: TestClient
) -> None:
    other_env = {**env, "SESSION_SECRET": "a-completely-different-secret"}
    other = create_app(Settings.from_env(other_env), provider_factory=lambda: None)
    with TestClient(other, base_url=BASE_URL) as other_client:
        login(other_client)
        forged = other_client.cookies.get(SESSION_COOKIE)
    probe_client.cookies.delete(SESSION_COOKIE)
    probe_client.cookies.set(SESSION_COOKIE, forged)
    assert probe_client.get("/probe").status_code == 401


def test_logout_clears_session(probe_client: TestClient) -> None:
    token = login(probe_client)
    assert probe_client.get("/probe").status_code == 200
    res = probe_client.post("/api/logout", headers={"X-CSRF-Token": token})
    assert res.status_code == 200
    assert probe_client.get("/probe").status_code == 401


def test_logout_without_csrf_token_is_rejected(probe_client: TestClient) -> None:
    login(probe_client)
    assert probe_client.post("/api/logout").status_code == 403
    assert probe_client.get("/probe").status_code == 200


# ---------------------------------------------------------------- 분당 5회 제한 (25.3)


def test_sixth_attempt_within_a_minute_is_rejected(client: TestClient) -> None:
    token = _login_token(client)
    for _ in range(5):
        assert _post_login(client, "wrong", token).status_code == 401
    res = _post_login(client, OWNER_PASSWORD, token)
    assert res.status_code == 429
    assert int(res.headers["Retry-After"]) >= 1
    assert SESSION_COOKIE not in client.cookies


def test_fifth_attempt_can_still_succeed(client: TestClient) -> None:
    token = _login_token(client)
    for _ in range(4):
        assert _post_login(client, "wrong", token).status_code == 401
    assert _post_login(client, OWNER_PASSWORD, token).status_code == 200


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_rate_limiter_allows_again_after_the_window() -> None:
    clock = _Clock()
    limiter = LoginRateLimiter(limit=5, window=60.0, clock=clock)
    assert all(limiter.allow("1.2.3.4") for _ in range(5))
    assert not limiter.allow("1.2.3.4")
    assert 1 <= limiter.retry_after("1.2.3.4") <= 61
    clock.now += 59
    assert not limiter.allow("1.2.3.4")
    clock.now += 2
    assert limiter.allow("1.2.3.4")


def test_rejected_attempts_do_not_extend_the_block() -> None:
    clock = _Clock()
    limiter = LoginRateLimiter(limit=2, window=60.0, clock=clock)
    assert limiter.allow("ip")
    assert limiter.allow("ip")
    for _ in range(50):
        clock.now += 1
        assert not limiter.allow("ip")
    clock.now += 11
    assert limiter.allow("ip")


def test_rate_limit_is_per_ip() -> None:
    limiter = LoginRateLimiter(limit=1, window=60.0, clock=_Clock())
    assert limiter.allow("a")
    assert not limiter.allow("a")
    assert limiter.allow("b")


# ---------------------------------------------------------------- 로그인 없는 요청 (25.4)


def test_unauthenticated_api_request_is_rejected(probe_client: TestClient) -> None:
    assert probe_client.get("/probe").status_code == 401


def test_unauthenticated_browser_navigation_redirects_to_login(probe_client: TestClient) -> None:
    res = probe_client.get("/probe", headers={"Accept": "text/html"}, follow_redirects=False)
    assert res.status_code == 303
    assert res.headers["location"] == "/login"


def test_unauthenticated_unknown_path_is_rejected_not_404(probe_client: TestClient) -> None:
    assert probe_client.get("/no-such-page").status_code == 401


def test_public_paths_need_no_login(probe_client: TestClient) -> None:
    assert probe_client.get("/healthz").status_code == 200
    assert probe_client.get("/api/csrf").status_code == 200
    assert probe_client.get("/login").status_code != 401  # 화면이 없으면 503, 있으면 200


def test_authenticated_request_passes(probe_client: TestClient) -> None:
    login(probe_client)
    assert probe_client.get("/probe").json() == {"ok": True}


# ---------------------------------------------------------------- CSRF (25.5)


def test_state_changing_request_without_csrf_token_is_rejected(probe_client: TestClient) -> None:
    login(probe_client)
    assert probe_client.post("/probe").status_code == 403


def test_state_changing_request_with_wrong_csrf_token_is_rejected(
    probe_client: TestClient,
) -> None:
    login(probe_client)
    assert probe_client.post("/probe", headers={"X-CSRF-Token": "0" * 64}).status_code == 403


def test_csrf_token_in_header_is_accepted(probe_client: TestClient) -> None:
    token = login(probe_client)
    assert probe_client.post("/probe", headers={"X-CSRF-Token": token}).status_code == 200


def test_csrf_token_in_form_is_accepted(probe_client: TestClient) -> None:
    token = login(probe_client)
    res = probe_client.post("/probe", data={"csrf_token": token, "x": "y"})
    assert res.status_code == 200


def test_csrf_token_from_another_session_is_rejected(
    probe_client: TestClient, app_with_routes
) -> None:
    login(probe_client)
    with TestClient(app_with_routes, base_url=BASE_URL) as other:
        other_token = login(other)
    assert probe_client.post("/probe", headers={"X-CSRF-Token": other_token}).status_code == 403


def test_login_post_requires_csrf_token(client: TestClient) -> None:
    client.get("/api/csrf")
    res = client.post("/api/login", json={"password": OWNER_PASSWORD})
    assert res.status_code == 403
    assert SESSION_COOKIE not in client.cookies


def test_login_post_without_anonymous_cookie_is_rejected(client: TestClient) -> None:
    token = _login_token(client)
    client.cookies.clear()
    res = client.post(
        "/api/login", json={"password": OWNER_PASSWORD}, headers={"X-CSRF-Token": token}
    )
    assert res.status_code == 403


def test_safe_methods_do_not_need_csrf_token(probe_client: TestClient) -> None:
    login(probe_client)
    assert probe_client.get("/probe").status_code == 200
    # HEAD는 이 경로에 등록되지 않아 405지만, CSRF 때문에 403이 되어서는 안 된다.
    assert probe_client.head("/probe").status_code != 403


def test_csrf_failure_message_does_not_leak_secrets(probe_client: TestClient) -> None:
    login(probe_client)
    res = probe_client.post("/probe")
    for secret in (OWNER_HASH, SESSION_SECRET):
        assert secret not in res.text
