"""자료 라우트 테스트: 상태 코드, 화면 조각, 파일 응답 헤더(요구사항 3, 5.6, 6, 8, 10.4, 11)."""

from __future__ import annotations

import io
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, func, select

from open_attendee.assets import SIZE_LIMITS
from open_attendee.config import Settings
from open_attendee.main import create_app
from open_attendee.models import Asset, AssetKind, DocChunk, MemoBlock, TranscriptSegment
from open_attendee.sessions import SessionService
from open_attendee.storage import LocalBlobStore
from tests.conftest import BASE_URL, csrf_token, login
from tests.documents import make_encrypted_pdf, make_pdf, make_pptx
from tests.imaging import make_exif, make_image

OWNER = "owner"  # 로그인한 소유자의 ID
JSON = {"Accept": "application/json"}
HX = {"HX-Request": "true"}
WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 32
WAV = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 32


def create_session(client: TestClient, title: str = "행사") -> str:
    res = client.post("/api/sessions", json={"title": title})
    assert res.status_code == 201, res.text
    return res.json()["id"]


def upload(
    client: TestClient,
    sid: str,
    kind: str,
    data: bytes,
    name: str = "file",
    headers: dict[str, str] | None = None,
    **fields: str,
):
    return client.post(
        f"/api/sessions/{sid}/assets",
        data={"kind": kind, **fields},
        files={"file": (name, data, "application/octet-stream")},
        headers={**JSON, **(headers or {})},
    )


def asset_count(db: Session, kind: AssetKind | None = None) -> int:
    query = select(func.count()).select_from(Asset)
    if kind is not None:
        query = query.where(Asset.kind == kind)
    return db.exec(query).one()


def blob_files(blobs: LocalBlobStore) -> list:
    return [p for p in blobs.root.rglob("*") if p.is_file()]


@pytest.fixture
def sid(auth_client: TestClient) -> str:
    return create_session(auth_client)


@pytest.fixture
def recording_client(env: dict[str, str]) -> Iterator[TestClient]:
    settings = Settings.from_env({**env, "FEATURE_RECORDING": "true", "TRANSCRIBER": "fake"})
    app = create_app(settings, provider_factory=lambda: None)
    with TestClient(app, base_url=BASE_URL) as test_client:
        login(test_client)
        test_client.headers["X-CSRF-Token"] = csrf_token(test_client)
        yield test_client


# ---------------------------------------------------------------------------- 기본 동작


def test_사진을_올리면_201과_정리된_사진_정보를_돌려준다(
    auth_client: TestClient, sid: str, blobs: LocalBlobStore
) -> None:
    raw = make_image((80, 40), exif=make_exif())
    res = upload(auth_client, sid, "photo", raw, "IMG_1.jpg")

    assert res.status_code == 201
    body = res.json()
    assert (body["kind"], body["mime"], body["display_name"]) == (
        "photo",
        "image/jpeg",
        "IMG_1.jpg",
    )
    assert body["status"] == "ready"
    saved = [p.read_bytes() for p in blob_files(blobs)]
    assert len(saved) == 2
    assert all(b"Exif" not in data and data != raw for data in saved)


def test_로그인_없이는_올릴_수_없다(client: TestClient) -> None:
    res = client.post(
        "/api/sessions/abc/assets",
        data={"kind": "photo"},
        files={"file": ("a.jpg", make_image(), "image/jpeg")},
    )
    assert res.status_code == 401


def test_CSRF_헤더가_없으면_403이고_저장하지_않는다(
    auth_client: TestClient, sid: str, db: Session, blobs: LocalBlobStore
) -> None:
    del auth_client.headers["X-CSRF-Token"]
    res = upload(auth_client, sid, "photo", make_image(), "a.jpg")
    assert res.status_code == 403
    assert asset_count(db) == 0
    assert blob_files(blobs) == []


def test_알_수_없는_종류는_422(auth_client: TestClient, sid: str) -> None:
    assert upload(auth_client, sid, "video", b"x").status_code == 422


def test_파일_필드가_없으면_422(auth_client: TestClient, sid: str) -> None:
    res = auth_client.post(f"/api/sessions/{sid}/assets", data={"kind": "photo"}, headers=JSON)
    assert res.status_code == 422


# ---------------------------------------------------------------------------- 상태 코드


@pytest.mark.parametrize(
    ("kind", "data"),
    [
        ("photo", make_pdf(["x"])),
        ("slides", make_image()),
        ("reference", make_image()),
        ("voice_memo", b"not audio at all"),
    ],
)
def test_매직_바이트가_맞지_않으면_415(
    auth_client: TestClient,
    sid: str,
    db: Session,
    blobs: LocalBlobStore,
    kind: str,
    data: bytes,
) -> None:
    res = upload(auth_client, sid, kind, data, "x.jpg", solo_voice="true")
    assert res.status_code == 415
    assert asset_count(db) == 0
    assert blob_files(blobs) == []


def test_확장자가_jpg여도_내용이_PDF면_415(auth_client: TestClient, sid: str) -> None:
    assert upload(auth_client, sid, "photo", make_pdf(["x"]), "fake.jpg").status_code == 415


def test_크기_상한을_넘으면_413(
    auth_client: TestClient,
    sid: str,
    db: Session,
    blobs: LocalBlobStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = make_image((40, 40))
    monkeypatch.setitem(SIZE_LIMITS, AssetKind.PHOTO, len(data) - 1)
    assert upload(auth_client, sid, "photo", data, "a.jpg").status_code == 413
    assert asset_count(db) == 0
    assert blob_files(blobs) == []


def test_200장이_차면_201번째_사진은_413(
    auth_client: TestClient, sid: str, db: Session, blobs: LocalBlobStore
) -> None:
    for i in range(199):
        db.add(Asset(session_id=sid, kind=AssetKind.PHOTO, display_name=f"{i}", mime="image/jpeg"))
    db.commit()

    assert upload(auth_client, sid, "photo", make_image(), "200th.jpg").status_code == 201
    files_after_200 = len(blob_files(blobs))
    res = upload(auth_client, sid, "photo", make_image(), "201st.jpg")

    assert res.status_code == 413
    assert asset_count(db, AssetKind.PHOTO) == 200
    assert len(blob_files(blobs)) == files_after_200


def test_발표자료는_20개까지(auth_client: TestClient, sid: str, db: Session) -> None:
    for i in range(20):
        db.add(Asset(session_id=sid, kind=AssetKind.SLIDES, display_name=f"{i}", mime="x"))
    db.commit()
    assert upload(auth_client, sid, "slides", make_pdf(["x"]), "deck.pdf").status_code == 413


def test_참고자료는_50개까지(auth_client: TestClient, sid: str, db: Session) -> None:
    for i in range(50):
        db.add(Asset(session_id=sid, kind=AssetKind.REFERENCE, display_name=f"{i}", mime="x"))
    db.commit()
    assert upload(auth_client, sid, "reference", b"notes", "n.txt").status_code == 413


def test_녹음은_플래그가_꺼져_있으면_503(
    auth_client: TestClient, sid: str, db: Session, blobs: LocalBlobStore
) -> None:
    res = upload(auth_client, sid, "recording", WEBM, "talk.webm")
    assert res.status_code == 503
    assert asset_count(db) == 0
    assert blob_files(blobs) == []


def test_동의_없는_녹음은_403이고_저장하지_않는다(
    recording_client: TestClient, db: Session, blobs: LocalBlobStore
) -> None:
    sid = create_session(recording_client)
    res = upload(recording_client, sid, "recording", WEBM, "talk.webm")
    assert res.status_code == 403
    assert asset_count(db) == 0
    assert blob_files(blobs) == []


def test_solo_voice가_아닌_음성_메모는_동의가_없으면_403(
    auth_client: TestClient, sid: str, db: Session
) -> None:
    assert upload(auth_client, sid, "voice_memo", WAV, "m.wav").status_code == 403
    res = upload(auth_client, sid, "voice_memo", WAV, "m.wav", solo_voice="true")
    assert res.status_code == 201
    assert asset_count(db) == 1


def test_동의_기록과_함께_올리면_녹음을_저장한다(recording_client: TestClient, db: Session) -> None:
    sid = create_session(recording_client)
    consent = recording_client.post(
        f"/api/sessions/{sid}/consents",
        data={
            "obtained_on": "2026-11-14",
            "method": "행사 시작 전 구두 공지",
            "informed_all": "true",
            "can_document": "true",
            "no_outside_disclosure": "true",
        },
    )
    assert consent.status_code == 201

    res = upload(
        recording_client, sid, "recording", WEBM, "talk.webm", consent_id=consent.json()["id"]
    )
    assert res.status_code == 201
    assert res.json()["status"] == "stored"


def test_깨진_PPTX는_422이고_저장하지_않는다(
    auth_client: TestClient, sid: str, db: Session, blobs: LocalBlobStore
) -> None:
    broken = io.BytesIO()
    with ZipFile(broken, "w") as archive:
        archive.writestr("ppt/presentation.xml", "<broken")
    res = upload(auth_client, sid, "slides", broken.getvalue(), "deck.pptx")
    assert res.status_code == 422
    assert "PPTX" in res.json()["detail"]
    assert asset_count(db) == 0
    assert blob_files(blobs) == []


def test_PPTX_업로드와_목록에_전체_슬라이드_수를_표시(auth_client: TestClient, sid: str) -> None:
    res = upload(auth_client, sid, "slides", make_pptx(["첫 장", "", "마지막 장"]), "deck.pptx")
    assert res.status_code == 201
    assert res.json()["page_count"] == 3
    item = auth_client.get(f"/api/sessions/{sid}/assets").json()["items"][0]
    assert item["page_count"] == 3
    assert item["chunk_count"] == 2


def test_PPTX_압축_해제_상한을_넘으면_저장하지_않는다(
    auth_client: TestClient,
    sid: str,
    db: Session,
    blobs: LocalBlobStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("open_attendee.processors.docs._MAX_PPTX_EXPANDED_BYTES", 1)
    result = upload(auth_client, sid, "slides", make_pptx(["제목"]), "deck.pptx")
    assert result.status_code == 413
    assert asset_count(db) == 0
    assert blob_files(blobs) == []


@pytest.mark.parametrize(
    ("kind", "data"),
    [
        ("photo", make_image()[:80]),
        ("slides", b"%PDF-1.4\nthis is not a pdf"),
        ("slides", make_encrypted_pdf()),
        ("reference", b"\xff\xfe\xfd\xfc\xfb"),
    ],
    ids=["깨진 사진", "깨진 PDF", "암호 PDF", "읽을 수 없는 텍스트"],
)
def test_깨진_파일과_암호_PDF는_422(
    auth_client: TestClient,
    sid: str,
    db: Session,
    blobs: LocalBlobStore,
    kind: str,
    data: bytes,
) -> None:
    res = upload(auth_client, sid, kind, data, "x.bin")
    assert res.status_code == 422
    assert isinstance(res.json()["detail"], str)
    assert asset_count(db) == 0
    assert blob_files(blobs) == []


def test_암호_PDF_오류는_이유를_알려_준다(auth_client: TestClient, sid: str) -> None:
    res = upload(auth_client, sid, "slides", make_encrypted_pdf(), "locked.pdf")
    assert "암호" in res.json()["detail"]


def test_저장_공간이_부족하면_507(
    auth_client: TestClient, sid: str, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from open_attendee.storage import StorageFull

    def full(self, key, data):  # type: ignore[no-untyped-def]
        raise StorageFull(28, "full")

    monkeypatch.setattr(LocalBlobStore, "put", full)
    res = upload(auth_client, sid, "photo", make_image(), "a.jpg")
    assert res.status_code == 507
    assert asset_count(db) == 0


def test_다른_소유자의_세션에는_올릴_수_없다(
    auth_client: TestClient, sessions: SessionService, db: Session
) -> None:
    foreign = sessions.create("someone-else", "남의 행사")
    assert upload(auth_client, foreign.id, "photo", make_image(), "a.jpg").status_code == 404
    assert auth_client.get(f"/api/sessions/{foreign.id}/assets").status_code == 404
    assert asset_count(db) == 0


# ---------------------------------------------------------------------------- 삭제


def test_삭제하면_행과_파생_데이터와_파일이_모두_사라진다(
    auth_client: TestClient, sid: str, db: Session, blobs: LocalBlobStore
) -> None:
    doc = upload(auth_client, sid, "slides", make_pdf(["Intro"]), "deck.pdf").json()
    photo = upload(auth_client, sid, "photo", make_image(), "a.jpg").json()
    db.add(TranscriptSegment(asset_id=doc["id"], start_ms=0, end_ms=5, text="전사"))
    db.commit()
    assert db.exec(select(func.count()).select_from(DocChunk)).one() == 1

    for asset in (doc, photo):
        res = auth_client.delete(f"/api/sessions/{sid}/assets/{asset['id']}")
        assert res.status_code == 204

    assert asset_count(db) == 0
    assert db.exec(select(func.count()).select_from(DocChunk)).one() == 0
    assert db.exec(select(func.count()).select_from(TranscriptSegment)).one() == 0
    assert blob_files(blobs) == []
    assert auth_client.delete(f"/api/sessions/{sid}/assets/{doc['id']}").status_code == 404


# ---------------------------------------------------------------------------- 설명과 연결


def test_사진_설명을_저장한다(auth_client: TestClient, sid: str, db: Session) -> None:
    photo = upload(auth_client, sid, "photo", make_image(), "a.jpg").json()
    url = f"/api/sessions/{sid}/assets/{photo['id']}/caption"

    res = auth_client.put(url, data={"caption": "화이트보드 사진"}, headers=JSON)
    assert res.json()["caption"] == "화이트보드 사진"
    assert db.get(Asset, photo["id"]).caption == "화이트보드 사진"  # type: ignore[union-attr]

    too_long = auth_client.put(url, data={"caption": "가" * 2001}, headers=JSON)
    assert too_long.status_code == 422
    assert db.get(Asset, photo["id"]).caption == "화이트보드 사진"  # type: ignore[union-attr]


def test_업로드_직후_사진은_5분_안의_메모에_자동으로_붙는다(
    auth_client: TestClient, sid: str, db: Session
) -> None:
    block_id = str(uuid.uuid4())
    auth_client.put(f"/api/sessions/{sid}/blocks/{block_id}", json={"text": "발표 메모"})
    far_block = str(uuid.uuid4())
    auth_client.put(f"/api/sessions/{sid}/blocks/{far_block}", json={"text": "한참 뒤"})
    db.get(MemoBlock, far_block).created_at = datetime.now(UTC) + timedelta(hours=2)  # type: ignore[union-attr]
    db.commit()

    res = upload(auth_client, sid, "photo", make_image(), "a.jpg")  # EXIF 시각 없음: 업로드 시각

    assert res.json()["linked_block_id"] == block_id
    item = auth_client.get(f"/api/sessions/{sid}/assets").json()["items"][0]
    assert (item["linked_block_id"], item["link_manual"]) == (block_id, False)


def test_멀리_떨어진_메모와는_연결하지_않는다(
    auth_client: TestClient, sid: str, db: Session
) -> None:
    block_id = str(uuid.uuid4())
    auth_client.put(f"/api/sessions/{sid}/blocks/{block_id}", json={"text": "예전 메모"})
    db.get(MemoBlock, block_id).created_at = datetime.now(UTC) - timedelta(hours=3)  # type: ignore[union-attr]
    db.commit()

    res = upload(auth_client, sid, "photo", make_image(), "a.jpg")
    assert res.json()["linked_block_id"] is None


def test_직접_지정한_연결은_자동_계산이_덮어쓰지_않는다(
    auth_client: TestClient, sid: str, db: Session
) -> None:
    near, other = str(uuid.uuid4()), str(uuid.uuid4())
    auth_client.put(f"/api/sessions/{sid}/blocks/{near}", json={"text": "가까운 메모"})
    auth_client.put(f"/api/sessions/{sid}/blocks/{other}", json={"text": "고른 메모"})
    photo = upload(auth_client, sid, "photo", make_image(), "a.jpg").json()
    link_url = f"/api/sessions/{sid}/assets/{photo['id']}/link"

    chosen = auth_client.put(link_url, data={"block_id": other}, headers=JSON)
    assert (chosen.json()["linked_block_id"], chosen.json()["link_manual"]) == (other, True)

    # 새 사진을 올리거나 화면을 다시 열어 자동 계산이 돌아도 지정한 연결이 남는다.
    upload(auth_client, sid, "photo", make_image(), "b.jpg")
    items = auth_client.get(f"/api/sessions/{sid}/assets").json()["items"]
    first = next(i for i in items if i["id"] == photo["id"])
    assert (first["linked_block_id"], first["link_manual"]) == (other, True)
    assert db.get(Asset, photo["id"]).linked_block_id == other  # type: ignore[union-attr]


def test_다른_세션의_메모에는_연결할_수_없다(
    auth_client: TestClient, sid: str, sessions: SessionService
) -> None:
    other_sid = create_session(auth_client, "다른 행사")
    foreign = str(uuid.uuid4())
    auth_client.put(f"/api/sessions/{other_sid}/blocks/{foreign}", json={"text": "x"})
    photo = upload(auth_client, sid, "photo", make_image(), "a.jpg").json()
    res = auth_client.put(
        f"/api/sessions/{sid}/assets/{photo['id']}/link", data={"block_id": foreign}, headers=JSON
    )
    assert res.status_code == 422


# ---------------------------------------------------------------------------- 목록


def test_목록은_청크_수와_녹음_가능_여부를_함께_돌려준다(auth_client: TestClient, sid: str) -> None:
    upload(auth_client, sid, "slides", make_pdf(["", ""]), "scan.pdf")
    upload(auth_client, sid, "slides", make_pdf(["Hello"]), "text.pdf")
    body = auth_client.get(f"/api/sessions/{sid}/assets").json()
    counts = {i["display_name"]: i["chunk_count"] for i in body["items"]}
    assert counts == {"scan.pdf": 0, "text.pdf": 1}
    assert body["recording_enabled"] is False
    assert body["limits"] == {"photo": 200, "slides": 20, "reference": 50}


def test_플래그가_켜져_있으면_녹음_가능으로_알린다(recording_client: TestClient) -> None:
    sid = create_session(recording_client)
    assert recording_client.get(f"/api/sessions/{sid}/assets").json()["recording_enabled"] is True


# ---------------------------------------------------------------------------- 파일 응답


def test_저장된_파일은_내려받기_헤더와_함께_나간다(auth_client: TestClient, sid: str) -> None:
    doc = upload(auth_client, sid, "reference", "한글 메모".encode(), "메모 파일.txt").json()
    res = auth_client.get(f"/api/sessions/{sid}/assets/{doc['id']}/file")

    assert res.status_code == 200
    assert res.content == "한글 메모".encode()
    assert res.headers["content-disposition"].startswith("attachment;")
    assert "filename*=UTF-8''" in res.headers["content-disposition"]
    assert res.headers["x-content-type-options"] == "nosniff"
    assert res.headers["content-type"].startswith("text/plain")


def test_사진과_축소판도_같은_헤더로_나간다(auth_client: TestClient, sid: str) -> None:
    photo = upload(auth_client, sid, "photo", make_image((900, 600)), "a.jpg").json()
    for suffix in ("file", "thumbnail"):
        res = auth_client.get(f"/api/sessions/{sid}/assets/{photo['id']}/{suffix}")
        assert res.status_code == 200
        assert res.headers["content-disposition"].startswith("attachment;")
        assert res.headers["x-content-type-options"] == "nosniff"
        assert res.content.startswith(b"\xff\xd8")
    assert (
        int(
            auth_client.get(f"/api/sessions/{sid}/assets/{photo['id']}/file").headers[
                "content-length"
            ]
        )
        == photo["size_bytes"]
    )


def test_파일_이름에_따옴표와_줄바꿈이_있어도_헤더가_깨지지_않는다(
    auth_client: TestClient, sid: str
) -> None:
    doc = upload(auth_client, sid, "reference", b"x", 'a"b\r\nX-Evil: 1.txt').json()
    res = auth_client.get(f"/api/sessions/{sid}/assets/{doc['id']}/file")
    assert "x-evil" not in {k.lower() for k in res.headers}
    assert '"' not in res.headers["content-disposition"].split('filename="')[1].split('"')[0]


def test_없는_파일과_다른_소유자의_파일은_404(
    auth_client: TestClient, sid: str, sessions: SessionService, db: Session
) -> None:
    assert auth_client.get(f"/api/sessions/{sid}/assets/nope/file").status_code == 404
    foreign = sessions.create("someone-else", "남의 행사")
    asset = Asset(session_id=foreign.id, kind=AssetKind.PHOTO, display_name="p", mime="image/jpeg")
    db.add(asset)
    db.commit()
    assert auth_client.get(f"/api/sessions/{foreign.id}/assets/{asset.id}/file").status_code == 404
    # 내 세션 주소로 남의 자료 ID를 불러도 마찬가지다.
    assert auth_client.get(f"/api/sessions/{sid}/assets/{asset.id}/file").status_code == 404


def test_로그인_없이는_파일을_받을_수_없다(client: TestClient) -> None:
    assert client.get("/api/sessions/a/assets/b/file").status_code == 401
