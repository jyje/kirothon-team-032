"""세션과 메모 라우트 테스트 (요구사항 1.1~1.5, 2.1~2.6, 25.7)."""

from __future__ import annotations

import io
import re
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from open_attendee.models import Asset, AssetKind
from open_attendee.sessions import SessionService
from open_attendee.storage import BlobNotFound, LocalBlobStore, make_key

OWNER = "owner"
HX = {"HX-Request": "true"}


def _create(client: TestClient, title: str = "AWSKRUG 밋업", event_date: str = "2026-11-14") -> str:
    res = client.post(
        "/sessions", data={"title": title, "event_date": event_date}, follow_redirects=False
    )
    assert res.status_code == 303, res.text
    match = re.fullmatch(r"/sessions/([0-9a-f]{32})", res.headers["location"])
    assert match
    return match.group(1)


def test_login_redirects_land_on_a_real_page(auth_client: TestClient) -> None:
    assert auth_client.get("/", follow_redirects=False).headers["location"] == "/sessions"
    assert auth_client.get("/sessions").status_code == 200


def test_sessions_require_login(client: TestClient) -> None:
    assert client.get("/sessions").status_code == 401
    assert client.post("/sessions", data={"title": "x"}).status_code == 401


def test_create_session_redirects_to_record_screen(auth_client: TestClient) -> None:
    sid = _create(auth_client)
    page = auth_client.get(f"/sessions/{sid}")
    assert page.status_code == 200
    assert "AWSKRUG 밋업" in page.text
    assert 'value="2026-11-14"' in page.text


@pytest.mark.parametrize("title", ["", "   ", "x" * 201])
def test_create_with_invalid_title_shows_error_and_creates_nothing(
    auth_client: TestClient, title: str
) -> None:
    res = auth_client.post("/sessions", data={"title": title}, follow_redirects=False)
    assert res.status_code == 422
    assert "1~200자" in res.text
    assert "세션이 없어요" in auth_client.get("/sessions").text


def test_create_with_invalid_date_shows_error(auth_client: TestClient) -> None:
    res = auth_client.post("/sessions", data={"title": "제목", "event_date": "2026-13-45"})
    assert res.status_code == 422
    assert "YYYY-MM-DD" in res.text
    assert 'value="제목"' in res.text  # 입력한 제목은 남겨 둔다


def test_list_shows_title_date_asset_count_and_draft_status(
    auth_client: TestClient, db: Session
) -> None:
    sid = _create(auth_client, "목록 확인", "2026-11-14")
    for _ in range(2):
        db.add(Asset(session_id=sid, kind=AssetKind.PHOTO, display_name="p", mime="i/j"))
    db.commit()
    html = auth_client.get("/sessions").text
    assert "목록 확인" in html
    assert "2026-11-14" in html
    assert "2개" in html
    assert "없음" in html  # 초안 상태


def test_titles_are_html_escaped(auth_client: TestClient) -> None:
    sid = _create(auth_client, "<script>alert(1)</script>")
    assert "<script>alert(1)</script>" not in auth_client.get("/sessions").text
    assert "<script>alert(1)</script>" not in auth_client.get(f"/sessions/{sid}").text


def test_patch_updates_title_and_date(auth_client: TestClient) -> None:
    sid = _create(auth_client)
    res = auth_client.patch(
        f"/sessions/{sid}", data={"title": "바뀐 제목", "event_date": ""}, headers=HX
    )
    assert res.status_code == 200
    page = auth_client.get(f"/sessions/{sid}").text
    assert "바뀐 제목" in page
    assert 'value="2026-11-14"' not in page


def test_patch_with_invalid_title_returns_error_fragment_for_htmx(
    auth_client: TestClient,
) -> None:
    sid = _create(auth_client)
    res = auth_client.patch(f"/sessions/{sid}", data={"title": ""}, headers=HX)
    assert res.status_code == 422
    assert res.headers["content-type"].startswith("text/html")
    assert "alert" in res.text
    assert "AWSKRUG 밋업" in auth_client.get(f"/sessions/{sid}").text


def test_delete_session_removes_it_and_asks_htmx_to_redirect(
    auth_client: TestClient, blobs: LocalBlobStore, db: Session
) -> None:
    sid = _create(auth_client)
    asset = Asset(session_id=sid, kind=AssetKind.PHOTO, display_name="p", mime="i/j")
    key = make_key(OWNER, sid, asset.id)
    asset.blob_key = key
    blobs.put(key, io.BytesIO(b"x"))
    db.add(asset)
    db.commit()

    res = auth_client.delete(f"/sessions/{sid}", headers=HX)
    assert res.status_code == 204
    assert res.headers["HX-Redirect"] == "/sessions"
    assert auth_client.get(f"/sessions/{sid}").status_code == 404
    with pytest.raises(BlobNotFound):
        blobs.open(key)


def test_block_save_uses_client_uuid_and_counts_revisions(auth_client: TestClient) -> None:
    sid = _create(auth_client)
    block_id = str(uuid.uuid4())
    url = f"/sessions/{sid}/blocks/{block_id}"
    first = auth_client.put(url, data={"text": "처음"}, headers={"Accept": "application/json"})
    second = auth_client.put(url, data={"text": "고침"}, headers={"Accept": "application/json"})
    assert first.json() == {"id": block_id, "revision": 1}
    assert second.json() == {"id": block_id, "revision": 2}
    page = auth_client.get(f"/sessions/{sid}").text
    assert "고침" in page
    assert "처음" not in page


def test_block_save_returns_status_fragment_for_htmx(auth_client: TestClient) -> None:
    sid = _create(auth_client)
    res = auth_client.put(
        f"/sessions/{sid}/blocks/{uuid.uuid4()}", data={"text": "메모"}, headers=HX
    )
    assert res.status_code == 200
    assert 'data-revision="1"' in res.text


def test_block_over_10000_chars_is_rejected(auth_client: TestClient) -> None:
    sid = _create(auth_client)
    block_id = str(uuid.uuid4())
    url = f"/sessions/{sid}/blocks/{block_id}"
    assert auth_client.put(url, data={"text": "가" * 10_000}).status_code == 200
    res = auth_client.put(url, data={"text": "가" * 10_001}, headers=HX)
    assert res.status_code == 422
    assert "10,000자" in res.text
    res = auth_client.put(url, data={"text": "가" * 10_001})
    assert res.status_code == 422
    assert "10,000자" in res.json()["detail"]


def test_block_with_non_uuid_id_is_rejected(auth_client: TestClient) -> None:
    sid = _create(auth_client)
    res = auth_client.put(f"/sessions/{sid}/blocks/not-a-uuid", data={"text": "x"})
    assert res.status_code == 422


def test_delete_block_returns_empty_body_so_htmx_removes_it(auth_client: TestClient) -> None:
    sid = _create(auth_client)
    block_id = str(uuid.uuid4())
    auth_client.put(f"/sessions/{sid}/blocks/{block_id}", data={"text": "지울 메모"})
    res = auth_client.delete(f"/sessions/{sid}/blocks/{block_id}", headers=HX)
    assert res.status_code == 200
    assert res.text == ""
    assert "지울 메모" not in auth_client.get(f"/sessions/{sid}").text
    assert auth_client.delete(f"/sessions/{sid}/blocks/{block_id}").status_code == 404


def test_record_screen_has_editor_summary_slot_and_mobile_layout(
    auth_client: TestClient,
) -> None:
    sid = _create(auth_client)
    page = auth_client.get(f"/sessions/{sid}").text
    assert 'id="composer"' in page
    assert 'id="photo-button"' in page
    assert f'hx-get="/sessions/{sid}/summary"' in page
    assert 'id="block-template"' in page
    assert 'role="tab"' in page  # 모바일 탭
    css = auth_client.get("/static/app.css").text
    mobile = css[css.index("@media (max-width: 700px)") :]
    assert ".dock" in mobile
    assert "position: sticky" in mobile
    assert "bottom:" in mobile


def test_record_screen_renders_saved_blocks_in_order(auth_client: TestClient) -> None:
    sid = _create(auth_client)
    ids = [str(uuid.uuid4()) for _ in range(3)]
    for i, block_id in enumerate(ids):
        auth_client.put(f"/sessions/{sid}/blocks/{block_id}", data={"text": f"메모-{i}"})
    page = auth_client.get(f"/sessions/{sid}").text
    positions = [page.index(f'data-block-id="{b}"') for b in ids]
    assert positions == sorted(positions)


def test_state_changing_routes_require_csrf_token(auth_client: TestClient) -> None:
    sid = _create(auth_client)
    auth_client.headers.pop("X-CSRF-Token")
    assert auth_client.post("/sessions", data={"title": "x"}).status_code == 403
    assert auth_client.patch(f"/sessions/{sid}", data={"title": "x"}).status_code == 403
    assert auth_client.delete(f"/sessions/{sid}").status_code == 403
    assert (
        auth_client.put(f"/sessions/{sid}/blocks/{uuid.uuid4()}", data={"text": "x"}).status_code
        == 403
    )


def test_other_owners_session_is_invisible_over_http(
    auth_client: TestClient, sessions: SessionService
) -> None:
    foreign = sessions.create("someone-else", "남의 세션")
    sessions.save_block("someone-else", foreign.id, str(uuid.uuid4()), "남의 비밀 메모")
    assert "남의 세션" not in auth_client.get("/sessions").text
    assert auth_client.get(f"/sessions/{foreign.id}").status_code == 404
    assert auth_client.patch(f"/sessions/{foreign.id}", data={"title": "x"}).status_code == 404
    assert auth_client.delete(f"/sessions/{foreign.id}").status_code == 404
    res = auth_client.put(f"/sessions/{foreign.id}/blocks/{uuid.uuid4()}", data={"text": "x"})
    assert res.status_code == 404
    assert sessions.get("someone-else", foreign.id).title == "남의 세션"
