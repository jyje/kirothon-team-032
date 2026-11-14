"""세션과 메모 블록 JSON API (요구사항 1, 2)."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from .conftest import OWNER_PASSWORD


@pytest.fixture
def api(client: TestClient) -> TestClient:
    token = client.get("/api/csrf").json()["csrf_token"]
    res = client.post(
        "/api/login", json={"password": OWNER_PASSWORD}, headers={"X-CSRF-Token": token}
    )
    client.headers["X-CSRF-Token"] = res.json()["csrf_token"]
    return client


def _create(api: TestClient, title: str = "밋업") -> str:
    res = api.post("/api/sessions", json={"title": title, "event_date": "2026-11-14"})
    assert res.status_code == 201
    return res.json()["id"]


def test_create_list_get_update_delete(api: TestClient) -> None:
    sid = _create(api)
    items = api.get("/api/sessions").json()["items"]
    assert [i["id"] for i in items] == [sid]
    assert items[0]["asset_count"] == 0
    assert items[0]["draft_status"] is None

    assert api.get(f"/api/sessions/{sid}").json()["blocks"] == []
    patched = api.patch(f"/api/sessions/{sid}", json={"title": "수정됨"}).json()
    assert patched["title"] == "수정됨"
    assert patched["event_date"] == "2026-11-14"  # 보내지 않은 필드는 그대로

    assert api.patch(f"/api/sessions/{sid}", json={"event_date": None}).json()["event_date"] is None
    assert api.delete(f"/api/sessions/{sid}").status_code == 204
    assert api.get(f"/api/sessions/{sid}").status_code == 404


@pytest.mark.parametrize("title", ["", "x" * 201])
def test_create_rejects_bad_title(api: TestClient, title: str) -> None:
    assert api.post("/api/sessions", json={"title": title}).status_code == 422


def test_block_revision_increases_on_each_save(api: TestClient) -> None:
    sid = _create(api)
    bid = str(uuid.uuid4())
    first = api.put(f"/api/sessions/{sid}/blocks/{bid}", json={"text": "하나"}).json()
    second = api.put(f"/api/sessions/{sid}/blocks/{bid}", json={"text": "둘"}).json()
    assert (first["revision"], second["revision"]) == (1, 2)
    blocks = api.get(f"/api/sessions/{sid}").json()["blocks"]
    assert [b["text"] for b in blocks] == ["둘"]
    assert api.delete(f"/api/sessions/{sid}/blocks/{bid}").status_code == 204
    assert api.get(f"/api/sessions/{sid}").json()["blocks"] == []


def test_block_over_limit_is_422(api: TestClient) -> None:
    sid = _create(api)
    res = api.put(f"/api/sessions/{sid}/blocks/{uuid.uuid4()}", json={"text": "가" * 10_001})
    assert res.status_code == 422


def test_write_without_csrf_header_is_403(api: TestClient) -> None:
    del api.headers["X-CSRF-Token"]
    assert api.post("/api/sessions", json={"title": "x"}).status_code == 403


def test_block_with_non_uuid_id_is_422(api: TestClient) -> None:
    sid = _create(api)
    assert api.put(f"/api/sessions/{sid}/blocks/not-a-uuid", json={"text": "x"}).status_code == 422
