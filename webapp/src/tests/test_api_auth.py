"""SPA용 JSON 인증 API (요구사항 25.1~25.5)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from .conftest import OWNER_PASSWORD


def _csrf(client: TestClient) -> tuple[str, bool]:
    body = client.get("/api/csrf").json()
    return body["csrf_token"], body["authenticated"]


def _post_login(client: TestClient, token: str, password: str):
    return client.post("/api/login", json={"password": password}, headers={"X-CSRF-Token": token})


def test_csrf_endpoint_is_public_and_reports_logged_out(client: TestClient) -> None:
    token, authenticated = _csrf(client)
    assert token
    assert authenticated is False


def test_login_with_right_password_sets_session_and_new_token(client: TestClient) -> None:
    token, _ = _csrf(client)
    res = _post_login(client, token, OWNER_PASSWORD)
    assert res.status_code == 200
    assert res.json()["authenticated"] is True
    assert res.json()["csrf_token"] != token  # 로그인하면 씨앗이 바뀐다
    new_token, authenticated = _csrf(client)
    assert authenticated is True
    assert new_token == res.json()["csrf_token"]


def test_login_with_wrong_password_is_401_json(client: TestClient) -> None:
    token, _ = _csrf(client)
    res = _post_login(client, token, "wrong")
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "invalid_password"
    assert _csrf(client)[1] is False


def test_login_without_csrf_header_is_403(client: TestClient) -> None:
    _csrf(client)
    res = client.post("/api/login", json={"password": OWNER_PASSWORD})
    assert res.status_code == 403


def test_login_is_rate_limited_after_five_attempts(client: TestClient) -> None:
    token, _ = _csrf(client)
    codes = [_post_login(client, token, "wrong").status_code for _ in range(6)]
    assert codes == [401, 401, 401, 401, 401, 429]


def test_logout_clears_session(client: TestClient) -> None:
    token, _ = _csrf(client)
    new_token = _post_login(client, token, OWNER_PASSWORD).json()["csrf_token"]
    res = client.post("/api/logout", headers={"X-CSRF-Token": new_token})
    assert res.status_code == 200
    assert _csrf(client)[1] is False


def test_protected_api_returns_401_without_login(client: TestClient) -> None:
    assert client.get("/api/sessions").status_code == 401
