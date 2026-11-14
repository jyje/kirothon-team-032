"""`AssetService` 단위 테스트(요구사항 3, 5.6, 6, 7, 8, 10.4, 11.3)."""

from __future__ import annotations

import io
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import func
from sqlmodel import Session, select

from open_attendee.assets import (
    COUNT_LIMITS,
    SIZE_LIMITS,
    THUMB_SUFFIX,
    AssetService,
    safe_display_name,
)
from open_attendee.config import Settings
from open_attendee.consent import ConsentForm, ConsentGate
from open_attendee.errors import (
    ConsentRequired,
    FeatureDisabled,
    NotFound,
    PayloadTooLarge,
    UnsupportedMediaType,
    ValidationFailed,
)
from open_attendee.models import (
    Asset,
    AssetKind,
    AssetStatus,
    DocChunk,
    EventSession,
    TranscriptSegment,
)
from open_attendee.sessions import SessionService
from open_attendee.storage import LocalBlobStore, StorageFull
from tests.documents import make_encrypted_pdf, make_pdf, make_pptx
from tests.imaging import make_exif, make_image, utc

OWNER = "owner-1"
OTHER = "owner-2"
WAV = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 32
WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 32


def stored_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*") if p.is_file()]


def count(db: Session, model: type) -> int:
    return db.exec(select(func.count()).select_from(model)).one()


@pytest.fixture
def recording_settings(env: dict[str, str]) -> Settings:
    return Settings.from_env({**env, "FEATURE_RECORDING": "true", "TRANSCRIBER": "fake"})


@pytest.fixture
def event(sessions: SessionService) -> EventSession:
    return sessions.create(OWNER, "행사")


@pytest.fixture
def assets(db: Session, blobs: LocalBlobStore, settings: Settings) -> AssetService:
    return AssetService(db, blobs, settings)


@pytest.fixture
def rec_assets(db: Session, blobs: LocalBlobStore, recording_settings: Settings) -> AssetService:
    return AssetService(db, blobs, recording_settings)


def make_consent(db: Session, session_id: str) -> str:
    form = ConsentForm(
        informed_all=True,
        can_document=True,
        no_outside_disclosure=True,
        obtained_on=date(2026, 11, 14),
        method="행사 시작 전 구두 공지",
    )
    return ConsentGate(db).record_consent(OWNER, session_id, form).id


def upload(
    service: AssetService,
    event: EventSession,
    kind: AssetKind,
    data: bytes,
    name: str = "file",
    **kwargs: object,
) -> Asset:
    return service.store_upload(OWNER, event.id, kind, name, io.BytesIO(data), **kwargs)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------- 사진


def test_사진은_EXIF를_지운_결과만_저장한다(
    assets: AssetService, event: EventSession, blobs: LocalBlobStore
) -> None:
    raw = make_image((80, 40), exif=make_exif(captured="2026:11:14 10:30:00"))
    asset = upload(assets, event, AssetKind.PHOTO, raw, "IMG_0001.JPG")

    assert asset.status is AssetStatus.READY
    assert asset.mime == "image/jpeg"
    assert asset.captured_at == utc("2026-11-14T10:30:00")
    assert asset.display_name == "IMG_0001.JPG"
    assert asset.blob_key is not None
    assert asset.blob_key.startswith(f"{OWNER}/{event.id}/")
    assert "IMG_0001" not in asset.blob_key

    with blobs.open(asset.blob_key) as saved:
        data = saved.read()
    assert data != raw
    assert b"Exif" not in data
    assert asset.size_bytes == len(data)
    with blobs.open(asset.blob_key + THUMB_SUFFIX) as thumb:
        assert thumb.read(2) == b"\xff\xd8"
    assert len(stored_files(blobs.root)) == 2  # 정리한 사진과 축소판뿐. 원본은 없다


def test_HEIC는_JPEG로_저장한다(assets: AssetService, event: EventSession) -> None:
    asset = upload(assets, event, AssetKind.PHOTO, make_image((40, 30), fmt="HEIF"), "a.heic")
    assert asset.mime == "image/jpeg"


def test_확장자가_아니라_매직_바이트로_판별한다(assets: AssetService, event: EventSession) -> None:
    asset = upload(assets, event, AssetKind.PHOTO, make_image(), "photo.txt")
    assert asset.mime == "image/jpeg"


@pytest.mark.parametrize(
    ("kind", "data"),
    [
        (AssetKind.PHOTO, make_pdf(["x"])),
        (AssetKind.PHOTO, b"GIF89a" + b"\x00" * 30),
        (AssetKind.SLIDES, make_image()),
        (AssetKind.SLIDES, b"plain text"),
        (AssetKind.REFERENCE, make_image()),
        (AssetKind.REFERENCE, b"abc\x00def"),
        (AssetKind.VOICE_MEMO, make_image()),
        (AssetKind.VOICE_MEMO, b"plain text file"),
    ],
)
def test_형식이_맞지_않으면_415이고_아무것도_저장하지_않는다(
    assets: AssetService, event: EventSession, blobs: LocalBlobStore, db: Session, kind, data
) -> None:
    with pytest.raises(UnsupportedMediaType):
        upload(assets, event, kind, data, solo_voice=True)
    assert stored_files(blobs.root) == []
    assert count(db, Asset) == 0


def test_깨진_사진은_422이고_저장하지_않는다(
    assets: AssetService, event: EventSession, blobs: LocalBlobStore, db: Session
) -> None:
    with pytest.raises(ValidationFailed):
        upload(assets, event, AssetKind.PHOTO, make_image()[:80])
    assert stored_files(blobs.root) == []
    assert count(db, Asset) == 0


# ---------------------------------------------------------------------------- 크기와 개수


def test_크기_상한을_넘으면_413(
    assets: AssetService,
    event: EventSession,
    blobs: LocalBlobStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = make_image((50, 50))
    monkeypatch.setitem(SIZE_LIMITS, AssetKind.PHOTO, len(data) - 1)
    with pytest.raises(PayloadTooLarge):
        upload(assets, event, AssetKind.PHOTO, data)
    assert stored_files(blobs.root) == []

    monkeypatch.setitem(SIZE_LIMITS, AssetKind.PHOTO, len(data))
    assert upload(assets, event, AssetKind.PHOTO, data).id  # 상한과 같으면 받는다


def test_크기_상한은_종류별로_정해진_값이다() -> None:
    mb = 1024 * 1024
    assert SIZE_LIMITS == {
        AssetKind.PHOTO: 20 * mb,
        AssetKind.SLIDES: 30 * mb,
        AssetKind.REFERENCE: 20 * mb,
        AssetKind.VOICE_MEMO: 50 * mb,
        AssetKind.RECORDING: 2048 * mb,
    }


class Unseekable(io.RawIOBase):
    """되감을 수 없는 스트림(네트워크 본문처럼)."""

    def __init__(self, data: bytes) -> None:
        self._buffer = io.BytesIO(data)

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return False

    def readinto(self, target) -> int:  # type: ignore[no-untyped-def]
        return self._buffer.readinto(target)


def test_되감을_수_없는_스트림도_크기를_센다(
    assets: AssetService, event: EventSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = make_image((50, 50))
    monkeypatch.setitem(SIZE_LIMITS, AssetKind.PHOTO, len(data) - 1)
    with pytest.raises(PayloadTooLarge):
        assets.store_upload(
            OWNER, event.id, AssetKind.PHOTO, "a.jpg", io.BufferedReader(Unseekable(data))
        )
    monkeypatch.setitem(SIZE_LIMITS, AssetKind.PHOTO, len(data))
    saved = assets.store_upload(
        OWNER, event.id, AssetKind.PHOTO, "a.jpg", io.BufferedReader(Unseekable(data))
    )
    assert saved.mime == "image/jpeg"


@pytest.mark.parametrize(
    ("kind", "data", "limit"),
    [
        (AssetKind.PHOTO, make_image(), 200),
        (AssetKind.SLIDES, make_pdf(["x"]), 20),
        (AssetKind.REFERENCE, b"text", 50),
    ],
)
def test_세션당_개수_상한을_넘으면_413(
    assets: AssetService,
    event: EventSession,
    blobs: LocalBlobStore,
    db: Session,
    kind: AssetKind,
    data: bytes,
    limit: int,
) -> None:
    assert COUNT_LIMITS[kind] == limit
    for i in range(limit):
        db.add(Asset(session_id=event.id, kind=kind, display_name=f"{i}", mime="x"))
    db.commit()

    with pytest.raises(PayloadTooLarge):
        upload(assets, event, kind, data)
    assert stored_files(blobs.root) == []
    assert count(db, Asset) == limit


def test_개수_상한은_세션별이고_종류별이다(
    assets: AssetService, sessions: SessionService, event: EventSession, db: Session
) -> None:
    for i in range(200):
        db.add(Asset(session_id=event.id, kind=AssetKind.PHOTO, display_name=f"{i}", mime="x"))
    db.commit()
    other = sessions.create(OWNER, "다른 행사")

    assert upload(assets, other, AssetKind.PHOTO, make_image()).id
    assert upload(assets, event, AssetKind.REFERENCE, b"notes").id


# ---------------------------------------------------------------------------- 동의와 기능 플래그


def test_녹음은_플래그가_꺼져_있으면_503(assets: AssetService, event: EventSession) -> None:
    with pytest.raises(FeatureDisabled):
        upload(assets, event, AssetKind.RECORDING, WEBM)


def test_녹음은_전사기가_none이면_503(
    db: Session, blobs: LocalBlobStore, env: dict[str, str], event: EventSession
) -> None:
    on_without_stt = Settings.from_env({**env, "FEATURE_RECORDING": "true"})
    service = AssetService(db, blobs, on_without_stt)
    with pytest.raises(FeatureDisabled):
        upload(service, event, AssetKind.RECORDING, WEBM)


def test_동의_없는_녹음은_403이고_파일을_저장하지_않는다(
    rec_assets: AssetService, event: EventSession, blobs: LocalBlobStore, db: Session
) -> None:
    with pytest.raises(ConsentRequired):
        upload(rec_assets, event, AssetKind.RECORDING, WEBM)
    assert stored_files(blobs.root) == []
    assert count(db, Asset) == 0


def test_동의가_있으면_녹음을_저장한다(
    rec_assets: AssetService, event: EventSession, db: Session
) -> None:
    consent_id = make_consent(db, event.id)
    asset = upload(rec_assets, event, AssetKind.RECORDING, WEBM, consent_id=consent_id)
    assert asset.consent_id == consent_id
    assert asset.status is AssetStatus.STORED
    assert asset.mime == "audio/webm"


def test_동의_기록이_철회되었거나_다른_세션의_것이면_403(
    rec_assets: AssetService, sessions: SessionService, event: EventSession, db: Session
) -> None:
    other = sessions.create(OWNER, "다른 행사")
    foreign = make_consent(db, other.id)
    revoked = make_consent(db, event.id)
    ConsentGate(db).revoke(OWNER, revoked)

    for consent_id in (foreign, revoked, "no-such-id", None):
        with pytest.raises(ConsentRequired):
            upload(rec_assets, event, AssetKind.RECORDING, WEBM, consent_id=consent_id)


def test_solo_voice가_아닌_음성_메모는_동의가_필요하다(
    assets: AssetService, event: EventSession, db: Session
) -> None:
    with pytest.raises(ConsentRequired):
        upload(assets, event, AssetKind.VOICE_MEMO, WAV, solo_voice=False)
    consent_id = make_consent(db, event.id)
    asset = upload(
        assets, event, AssetKind.VOICE_MEMO, WAV, solo_voice=False, consent_id=consent_id
    )
    assert asset.mime == "audio/wav"


def test_혼자_한_음성_메모는_동의_없이_저장한다(
    assets: AssetService, event: EventSession, db: Session
) -> None:
    other_consent = make_consent(db, event.id)
    asset = upload(
        assets, event, AssetKind.VOICE_MEMO, WAV, solo_voice=True, consent_id=other_consent
    )
    assert asset.solo_voice is True
    assert asset.consent_id is None  # 필요 없는 동의 기록은 붙이지 않는다


def test_solo_voice는_음성_메모에만_적용된다(rec_assets: AssetService, event: EventSession) -> None:
    with pytest.raises(ConsentRequired):
        upload(rec_assets, event, AssetKind.RECORDING, WEBM, solo_voice=True)


# ---------------------------------------------------------------------------- 문서


def test_PDF_발표자료는_쪽_번호가_붙은_조각으로_저장한다(
    assets: AssetService, event: EventSession, db: Session
) -> None:
    asset = upload(assets, event, AssetKind.SLIDES, make_pdf(["Intro", "", "Closing"]), "deck.pdf")

    chunks = db.exec(select(DocChunk).where(DocChunk.asset_id == asset.id)).all()
    assert sorted((c.page, c.part, c.text) for c in chunks) == [(1, 0, "Intro"), (3, 0, "Closing")]
    assert asset.status is AssetStatus.READY
    assert asset.mime == "application/pdf"
    assert assets.chunk_counts(event.id) == {asset.id: 2}


def test_텍스트가_없는_PDF도_저장하고_조각은_0개다(
    assets: AssetService, event: EventSession, db: Session
) -> None:
    asset = upload(assets, event, AssetKind.SLIDES, make_pdf(["", ""]), "scan.pdf")
    assert asset.status is AssetStatus.READY
    assert asset.blob_key is not None
    assert count(db, DocChunk) == 0
    assert assets.chunk_counts(event.id).get(asset.id, 0) == 0


def test_암호_PDF는_422이고_저장하지_않는다(
    assets: AssetService, event: EventSession, blobs: LocalBlobStore, db: Session
) -> None:
    with pytest.raises(ValidationFailed, match="암호"):
        upload(assets, event, AssetKind.SLIDES, make_encrypted_pdf())
    assert stored_files(blobs.root) == []
    assert count(db, Asset) == 0


def test_깨진_PDF는_422이고_저장하지_않는다(
    assets: AssetService, event: EventSession, blobs: LocalBlobStore, db: Session
) -> None:
    with pytest.raises(ValidationFailed):
        upload(assets, event, AssetKind.REFERENCE, b"%PDF-1.4\nthis is not a pdf")
    assert stored_files(blobs.root) == []
    assert count(db, Asset) == 0


def test_PPTX_발표자료는_415와_PDF_변환_안내(
    assets: AssetService, event: EventSession, blobs: LocalBlobStore, db: Session
) -> None:
    with pytest.raises(UnsupportedMediaType, match="PDF"):
        upload(assets, event, AssetKind.SLIDES, make_pptx(["제목"]), "deck.pptx")
    assert stored_files(blobs.root) == []
    assert count(db, Asset) == 0


def test_PPTX가_아닌_압축_파일은_415(assets: AssetService, event: EventSession) -> None:
    import zipfile

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("a.txt", "hello")
    with pytest.raises(UnsupportedMediaType):
        upload(assets, event, AssetKind.SLIDES, out.getvalue(), "x.zip")


def test_참고자료_TXT와_MD를_저장한다(
    assets: AssetService, event: EventSession, db: Session
) -> None:
    txt = upload(assets, event, AssetKind.REFERENCE, "첫 줄\n둘째 줄".encode(), "notes.txt")
    md = upload(assets, event, AssetKind.REFERENCE, b"# Title\n\nbody", "notes.md")
    pdf = upload(assets, event, AssetKind.REFERENCE, make_pdf(["Ref"]), "paper.pdf")

    assert (txt.mime, md.mime, pdf.mime) == ("text/plain", "text/markdown", "application/pdf")
    first = db.exec(select(DocChunk).where(DocChunk.asset_id == txt.id)).one()
    assert (first.page, first.part, first.text) == (1, 0, "첫 줄\n둘째 줄")


def test_UTF8이_아닌_텍스트도_CP949로_읽는다(
    assets: AssetService, event: EventSession, db: Session
) -> None:
    asset = upload(assets, event, AssetKind.REFERENCE, "한글 메모".encode("cp949"), "old.txt")
    chunk = db.exec(select(DocChunk).where(DocChunk.asset_id == asset.id)).one()
    assert chunk.text == "한글 메모"


def test_읽을_수_없는_인코딩의_텍스트는_422(assets: AssetService, event: EventSession) -> None:
    with pytest.raises(ValidationFailed):
        upload(assets, event, AssetKind.REFERENCE, b"\xff\xfe\xfd\xfc\xfb", "bad.txt")


# ---------------------------------------------------------------------------- 파일 이름과 저장소


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("../../etc/passwd", "passwd"),
        ("C:\\Users\\me\\a.jpg", "a.jpg"),
        ("a\x00b\nc.jpg", "abc.jpg"),
        ("", "파일"),
        ("x" * 400 + ".jpg", ("x" * 400)[:255]),
    ],
)
def test_표시_이름은_경로와_제어_문자를_뺀다(raw: str, expected: str) -> None:
    assert safe_display_name(raw) == expected


def test_원래_파일_이름은_저장_경로에_쓰지_않는다(
    assets: AssetService, event: EventSession, blobs: LocalBlobStore
) -> None:
    asset = upload(assets, event, AssetKind.PHOTO, make_image(), "../../evil name.jpg")
    assert asset.display_name == "evil name.jpg"
    assert all("evil" not in str(p) for p in stored_files(blobs.root))


class FullStore(LocalBlobStore):
    """두 번째 파일부터 용량 부족을 내는 저장소."""

    def __init__(self, root: Path, fail_on: int) -> None:
        super().__init__(root)
        self.puts = 0
        self.fail_on = fail_on

    def put(self, key: str, data) -> int:  # type: ignore[no-untyped-def]
        self.puts += 1
        if self.puts >= self.fail_on:
            raise StorageFull(28, "full")
        return super().put(key, data)


def test_용량_부족이면_StorageFull을_내고_쓴_파일을_지운다(
    db: Session, settings: Settings, tmp_path: Path, event: EventSession
) -> None:
    store = FullStore(tmp_path / "full", fail_on=2)  # 사진은 먼저 쓰고 축소판에서 실패
    service = AssetService(db, store, settings)
    with pytest.raises(StorageFull):
        upload(service, event, AssetKind.PHOTO, make_image())
    assert stored_files(store.root) == []
    assert count(db, Asset) == 0


# ---------------------------------------------------------------------------- 설명, 연결, 삭제


def test_사진_설명을_저장하고_비울_수_있다(assets: AssetService, event: EventSession) -> None:
    photo = upload(assets, event, AssetKind.PHOTO, make_image())
    assert assets.set_caption(OWNER, event.id, photo.id, "  화이트보드  ").caption == "화이트보드"
    assert assets.set_caption(OWNER, event.id, photo.id, "   ").caption is None
    with pytest.raises(ValidationFailed):
        assets.set_caption(OWNER, event.id, photo.id, "가" * 2001)


def test_설명은_사진에만_붙인다(assets: AssetService, event: EventSession) -> None:
    doc = upload(assets, event, AssetKind.REFERENCE, b"text")
    with pytest.raises(ValidationFailed):
        assets.set_caption(OWNER, event.id, doc.id, "x")


def test_수동_연결은_표시가_남고_다른_세션_블록은_거부한다(
    assets: AssetService, sessions: SessionService, event: EventSession
) -> None:
    block_id = "11111111-1111-4111-8111-111111111111"
    sessions.save_block(OWNER, event.id, block_id, "메모")
    other = sessions.create(OWNER, "다른 행사")
    foreign = "22222222-2222-4222-8222-222222222222"
    sessions.save_block(OWNER, other.id, foreign, "남의 메모")
    photo = upload(assets, event, AssetKind.PHOTO, make_image())
    assert photo.link_manual is False

    linked = assets.set_link(OWNER, event.id, photo.id, block_id)
    assert (linked.linked_block_id, linked.link_manual) == (block_id, True)
    with pytest.raises(ValidationFailed):
        assets.set_link(OWNER, event.id, photo.id, foreign)
    cleared = assets.set_link(OWNER, event.id, photo.id, None)
    assert (cleared.linked_block_id, cleared.link_manual) == (None, True)


def test_삭제하면_행과_파생_데이터와_파일이_모두_사라진다(
    assets: AssetService, event: EventSession, blobs: LocalBlobStore, db: Session
) -> None:
    doc = upload(assets, event, AssetKind.SLIDES, make_pdf(["Intro"]))
    photo = upload(assets, event, AssetKind.PHOTO, make_image())
    db.add(TranscriptSegment(asset_id=doc.id, start_ms=0, end_ms=10, text="전사"))
    db.commit()
    assert len(stored_files(blobs.root)) == 3

    assets.delete(OWNER, event.id, doc.id)
    assets.delete(OWNER, event.id, photo.id)

    assert count(db, Asset) == 0
    assert count(db, DocChunk) == 0
    assert count(db, TranscriptSegment) == 0
    assert stored_files(blobs.root) == []
    with pytest.raises(NotFound):
        assets.delete(OWNER, event.id, doc.id)


def test_삭제는_같은_세션의_다른_자료를_건드리지_않는다(
    assets: AssetService, event: EventSession, db: Session
) -> None:
    keep = upload(assets, event, AssetKind.SLIDES, make_pdf(["Keep"]))
    gone = upload(assets, event, AssetKind.SLIDES, make_pdf(["Gone"]))
    assets.delete(OWNER, event.id, gone.id)

    remaining = db.exec(select(DocChunk)).all()
    assert [c.asset_id for c in remaining] == [keep.id]


# ---------------------------------------------------------------------------- 소유자


def test_다른_소유자의_세션과_자료는_없는_것처럼_보인다(
    assets: AssetService, event: EventSession
) -> None:
    photo = upload(assets, event, AssetKind.PHOTO, make_image())
    with pytest.raises(NotFound):
        assets.store_upload(OTHER, event.id, AssetKind.PHOTO, "a.jpg", io.BytesIO(make_image()))
    with pytest.raises(NotFound):
        assets.get(OTHER, event.id, photo.id)
    with pytest.raises(NotFound):
        assets.delete(OTHER, event.id, photo.id)
    with pytest.raises(NotFound):
        assets.set_caption(OTHER, event.id, photo.id, "x")
    with pytest.raises(NotFound):
        assets.list(OTHER, event.id)
    with pytest.raises(NotFound):
        assets.open_file(OTHER, event.id, photo.id)


def test_자료_ID가_다른_세션의_것이면_없는_것처럼_보인다(
    assets: AssetService, sessions: SessionService, event: EventSession
) -> None:
    photo = upload(assets, event, AssetKind.PHOTO, make_image())
    other = sessions.create(OWNER, "다른 행사")
    with pytest.raises(NotFound):
        assets.get(OWNER, other.id, photo.id)


def test_저장한_파일을_열고_축소판도_열_수_있다(assets: AssetService, event: EventSession) -> None:
    photo = upload(assets, event, AssetKind.PHOTO, make_image())
    with assets.open_file(OWNER, event.id, photo.id).stream as full:
        assert full.read(2) == b"\xff\xd8"
    with assets.open_file(OWNER, event.id, photo.id, thumbnail=True).stream as thumb:
        assert thumb.read(2) == b"\xff\xd8"
    doc = upload(assets, event, AssetKind.REFERENCE, b"text")
    with pytest.raises(NotFound):
        assets.open_file(OWNER, event.id, doc.id, thumbnail=True)
