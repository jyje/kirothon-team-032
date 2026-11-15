"""`AssetService`: 업로드 검사와 저장, 설명과 연결 지정, 삭제(요구사항 3, 5.6, 6, 7, 8, 10.4, 11.3).

규칙은 모두 파일을 저장하기 전에 확인한다. 검사에서 걸리면 Blob 저장소와 DB에 아무것도 남지 않는다.
모든 조회와 변경은 `owner_id`로 한정한다(요구사항 25.7).

저장 방식
- 파일은 `<owner>/<session>/<asset_uuid>` 키로 저장한다. 원래 파일 이름은 `display_name`에만 둔다.
- 사진은 `PhotoProcessor.sanitize`가 만든 결과만 저장한다. 원본은 어디에도 두지 않는다.
  축소판은 같은 키에 `.thumb`를 붙인 키로 저장한다(열을 늘리지 않으려는 선택).
- 문서(발표자료, 참고자료)는 원본 그대로 저장하고, 저장 직후 `DocChunk`를 만든다.
  텍스트가 없는 문서는 `READY` 상태에 `DocChunk`가 0개인 자료다. 화면이 "텍스트 없음"으로 보여 준다.
"""

from __future__ import annotations

import contextlib
import io
import os
import tempfile
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import BinaryIO, Final

from sqlalchemy import delete, func
from sqlmodel import Session, select

from open_attendee.config import Settings
from open_attendee.consent import ConsentGate
from open_attendee.errors import (
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
    MemoBlock,
    TranscriptSegment,
)
from open_attendee.processors.docs import PPTX_MIME, DocExtractor
from open_attendee.processors.photo import PhotoProcessor, link_photos
from open_attendee.storage import BlobStore, make_key

MB: Final = 1024 * 1024
# 종류별 크기 상한(요구사항 8.3)과 세션당 개수 상한(3.1, 6.5, 7.2).
SIZE_LIMITS: Final[dict[AssetKind, int]] = {
    AssetKind.PHOTO: 20 * MB,
    AssetKind.SLIDES: 30 * MB,
    AssetKind.REFERENCE: 20 * MB,
    AssetKind.VOICE_MEMO: 50 * MB,
    AssetKind.RECORDING: 2048 * MB,
}
COUNT_LIMITS: Final[dict[AssetKind, int]] = {
    AssetKind.PHOTO: 200,
    AssetKind.SLIDES: 20,
    AssetKind.REFERENCE: 50,
}
KIND_LABELS: Final[dict[AssetKind, str]] = {
    AssetKind.PHOTO: "사진",
    AssetKind.SLIDES: "발표자료",
    AssetKind.REFERENCE: "참고자료",
    AssetKind.VOICE_MEMO: "음성 메모",
    AssetKind.RECORDING: "녹음",
}
CAPTION_MAX: Final = 2000
FILENAME_MAX: Final = 255
THUMB_SUFFIX: Final = ".thumb"

JPEG_MIME: Final = "image/jpeg"
PNG_MIME: Final = "image/png"
HEIC_MIME: Final = "image/heic"
PDF_MIME: Final = "application/pdf"
TEXT_MIME: Final = "text/plain"
MARKDOWN_MIME: Final = "text/markdown"

_HEIC_BRANDS: Final = frozenset(
    {b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"hevm", b"hevs", b"mif1", b"msf1"}
)
_SNIFF_BYTES: Final = 8192
_SPOOL_MEMORY: Final = 8 * MB
_MARKDOWN_EXTENSIONS: Final = frozenset({".md", ".markdown"})


# ---------------------------------------------------------------------------- 형식 판별


def _brand(head: bytes) -> bytes | None:
    """ISO 미디어 파일(`ftyp` 상자)의 브랜드. 아니면 `None`."""
    return head[8:12] if head[4:8] == b"ftyp" and len(head) >= 12 else None


def _is_pptx(stream: BinaryIO) -> bool:
    try:
        with zipfile.ZipFile(stream) as archive:
            return "ppt/presentation.xml" in archive.namelist()
    except (zipfile.BadZipFile, OSError, ValueError):
        return False
    finally:
        stream.seek(0)


def detect_mime(kind: AssetKind, head: bytes, stream: BinaryIO, filename: str = "") -> str | None:
    """파일 앞부분(매직 바이트)으로 형식을 판별한다. 확장자는 텍스트의 TXT/MD 구분에만 쓴다.

    자료 종류가 허용하지 않는 형식이면 `None`.
    """
    brand = _brand(head)
    if kind is AssetKind.PHOTO:
        if head.startswith(b"\xff\xd8\xff"):
            return JPEG_MIME
        if head.startswith(b"\x89PNG\r\n\x1a\n"):
            return PNG_MIME
        return HEIC_MIME if brand in _HEIC_BRANDS else None
    if kind is AssetKind.SLIDES:
        if head.startswith(b"%PDF-"):
            return PDF_MIME
        return PPTX_MIME if head.startswith(b"PK\x03\x04") and _is_pptx(stream) else None
    if kind is AssetKind.REFERENCE:
        if head.startswith(b"%PDF-"):
            return PDF_MIME
        if b"\x00" in head:  # 이진 파일
            return None
        suffix = PurePosixPath(filename.lower()).suffix
        return MARKDOWN_MIME if suffix in _MARKDOWN_EXTENSIONS else TEXT_MIME
    # 음성 메모와 녹음: webm, m4a(mp4), mp3, wav
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        return "audio/webm"
    if brand is not None and brand not in _HEIC_BRANDS:
        return "audio/mp4"
    if head.startswith(b"ID3") or (len(head) >= 2 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0):
        return "audio/mpeg"
    if head.startswith(b"RIFF") and head[8:12] == b"WAVE":
        return "audio/wav"
    return None


def safe_display_name(filename: str) -> str:
    """경로와 제어 문자를 뺀 표시용 이름. 저장 경로에는 쓰지 않는다."""
    name = PurePosixPath(filename.replace("\\", "/")).name
    name = "".join(ch for ch in name if ch.isprintable()).strip()
    return name[:FILENAME_MAX] or "파일"


@contextlib.contextmanager
def _bounded(stream: BinaryIO, limit: int, label: str) -> Iterator[tuple[BinaryIO, int]]:
    """크기를 재고 상한을 넘으면 `PayloadTooLarge`. 되감을 수 없는 스트림은 임시 파일에 받는다."""
    too_large = PayloadTooLarge(f"{label} 파일은 {limit // MB:,}MB까지 올릴 수 있어요.")
    if stream.seekable():
        stream.seek(0, os.SEEK_END)
        size = stream.tell()
        stream.seek(0)
        if size > limit:
            raise too_large
        yield stream, size
        return
    with tempfile.SpooledTemporaryFile(max_size=_SPOOL_MEMORY) as spool:
        size = 0
        while chunk := stream.read(MB):
            size += len(chunk)
            if size > limit:
                raise too_large
            spool.write(chunk)
        spool.seek(0)
        yield spool, size  # type: ignore[misc]


@dataclass(frozen=True)
class OpenedBlob:
    asset: Asset
    stream: BinaryIO


class AssetService:
    def __init__(
        self,
        db: Session,
        blobs: BlobStore,
        settings: Settings,
        *,
        photos: PhotoProcessor | None = None,
        docs: DocExtractor | None = None,
    ) -> None:
        self.db = db
        self.blobs = blobs
        self.settings = settings
        self.photos = photos or PhotoProcessor()
        self.docs = docs or DocExtractor()
        self.gate = ConsentGate(db)

    # ------------------------------------------------------------------ 조회

    def _session(self, owner_id: str, session_id: str) -> EventSession:
        event = self.db.exec(
            select(EventSession).where(
                EventSession.id == session_id, EventSession.owner_id == owner_id
            )
        ).one_or_none()
        if event is None:
            raise NotFound("세션을 찾을 수 없어요.")
        return event

    def get(self, owner_id: str, session_id: str, asset_id: str) -> Asset:
        self._session(owner_id, session_id)
        asset = self.db.get(Asset, asset_id)
        if asset is None or asset.session_id != session_id:
            raise NotFound("자료를 찾을 수 없어요.")
        return asset

    def list(self, owner_id: str, session_id: str) -> list[Asset]:
        self._session(owner_id, session_id)
        return list(
            self.db.exec(
                select(Asset).where(Asset.session_id == session_id).order_by(Asset.created_at)
            )
        )

    def open_file(
        self, owner_id: str, session_id: str, asset_id: str, *, thumbnail: bool = False
    ) -> OpenedBlob:
        """저장된 파일을 연다. 원본이 지워진 자료는 `NotFound`."""
        asset = self.get(owner_id, session_id, asset_id)
        if asset.blob_key is None or (thumbnail and asset.kind is not AssetKind.PHOTO):
            raise NotFound("파일을 찾을 수 없어요.")
        key = asset.blob_key + THUMB_SUFFIX if thumbnail else asset.blob_key
        try:
            return OpenedBlob(asset, self.blobs.open(key))
        except FileNotFoundError as exc:
            raise NotFound("파일을 찾을 수 없어요.") from exc

    def chunk_counts(self, session_id: str) -> dict[str, int]:
        """자료마다 `DocChunk` 개수. 문서인데 0이면 화면이 "텍스트 없음"을 보여 준다."""
        rows = self.db.exec(
            select(DocChunk.asset_id, func.count())
            .join(Asset, Asset.id == DocChunk.asset_id)  # type: ignore[arg-type]
            .where(Asset.session_id == session_id)
            .group_by(DocChunk.asset_id)
        )
        return dict(rows.all())  # type: ignore[arg-type]

    # ------------------------------------------------------------------ 업로드

    def store_upload(
        self,
        owner_id: str,
        session_id: str,
        kind: AssetKind,
        filename: str,
        stream: BinaryIO,
        consent_id: str | None = None,
        solo_voice: bool = False,
    ) -> Asset:
        """검사를 모두 통과한 파일만 저장한다.

        오류: 소유자 불일치 `NotFound`(404), 동의 없음 `ConsentRequired`(403),
        형식 `UnsupportedMediaType`(415), 크기와 개수 `PayloadTooLarge`(413),
        깨진 파일과 암호 PDF `ValidationFailed`(422), 꺼진 기능 `FeatureDisabled`(503),
        저장 공간 `StorageFull`(507).
        """
        self._session(owner_id, session_id)
        label = KIND_LABELS[kind]
        if kind is AssetKind.RECORDING and (
            not self.settings.feature_recording or self.settings.transcriber == "none"
        ):
            raise FeatureDisabled("녹음 기능이 꺼져 있어요.")

        asset = Asset(
            session_id=session_id,
            kind=kind,
            display_name=safe_display_name(filename),
            mime="",
            solo_voice=solo_voice if kind is AssetKind.VOICE_MEMO else False,
            consent_id=consent_id,
        )
        if self.gate.needs_consent(asset):
            self.gate.require_consent(asset)  # 유효한 동의가 없으면 ConsentRequired
        else:
            asset.consent_id = None

        self._check_count(session_id, kind, label)
        with _bounded(stream, SIZE_LIMITS[kind], label) as (source, size):
            head = source.read(_SNIFF_BYTES)
            source.seek(0)
            mime = detect_mime(kind, head, source, filename)
            if mime is None:
                raise UnsupportedMediaType(f"{label}으로 올릴 수 없는 파일 형식이에요.")
            asset.mime = mime
            asset.size_bytes = size
            if kind is AssetKind.PHOTO:
                return self._store_photo(owner_id, asset, source)
            if kind in (AssetKind.SLIDES, AssetKind.REFERENCE):
                return self._store_document(owner_id, asset, source)
            return self._store_audio(owner_id, asset, source)

    def _check_count(self, session_id: str, kind: AssetKind, label: str) -> None:
        limit = COUNT_LIMITS.get(kind)
        if limit is None:
            return
        count = self.db.exec(
            select(func.count())
            .select_from(Asset)
            .where(Asset.session_id == session_id, Asset.kind == kind)
        ).one()
        if count >= limit:
            raise PayloadTooLarge(f"{label}은 세션당 {limit}개까지 올릴 수 있어요.")

    def _store_photo(self, owner_id: str, asset: Asset, source: BinaryIO) -> Asset:
        clean = self.photos.sanitize(source.read())  # 깨진 파일은 InvalidImage(422)
        asset.mime = clean.mime
        asset.size_bytes = len(clean.data)
        asset.captured_at = clean.captured_at
        asset.status = AssetStatus.READY
        key = make_key(owner_id, asset.session_id, asset.id)
        return self._commit(
            asset,
            {key: io.BytesIO(clean.data), key + THUMB_SUFFIX: io.BytesIO(clean.thumbnail)},
        )

    def _store_document(self, owner_id: str, asset: Asset, source: BinaryIO) -> Asset:
        if not self.docs.supports(asset.mime, asset.kind):
            raise UnsupportedMediaType(
                f"{KIND_LABELS[asset.kind]}으로 올릴 수 없는 파일 형식이에요."
            )
        extraction = self.docs.extract(asset, source)  # 깨진 파일과 암호 PDF는 422
        asset.page_count = extraction.page_count
        source.seek(0)
        asset.status = AssetStatus.READY
        key = make_key(owner_id, asset.session_id, asset.id)
        return self._commit(asset, {key: source}, chunks=extraction.chunks)

    def _store_audio(self, owner_id: str, asset: Asset, source: BinaryIO) -> Asset:
        asset.status = AssetStatus.STORED
        key = make_key(owner_id, asset.session_id, asset.id)
        return self._commit(asset, {key: source})

    def _commit(
        self,
        asset: Asset,
        blobs: dict[str, BinaryIO],
        chunks: list[DocChunk] | None = None,
    ) -> Asset:
        """파일을 쓰고 DB에 기록한다. 어느 쪽이든 실패하면 쓴 파일을 지워 찌꺼기를 남기지 않는다."""
        written: list[str] = []
        try:
            for key, content in blobs.items():
                self.blobs.put(key, content)
                written.append(key)
            asset.blob_key = next(iter(blobs))
            self.db.add(asset)
            self.db.add_all(chunks or [])
            self.db.commit()
        except BaseException:
            self.db.rollback()
            for key in written:
                with contextlib.suppress(OSError):
                    self.blobs.delete(key)
            raise
        self.db.refresh(asset)
        return asset

    # ------------------------------------------------------------------ 설명과 연결

    def set_caption(
        self, owner_id: str, session_id: str, asset_id: str, caption: str | None
    ) -> Asset:
        """사진 설명을 저장한다. 비우면 설명을 지운다(요구사항 3.9)."""
        asset = self.get(owner_id, session_id, asset_id)
        if asset.kind is not AssetKind.PHOTO:
            raise ValidationFailed("설명은 사진에만 붙일 수 있어요.")
        text = (caption or "").strip()
        if len(text) > CAPTION_MAX:
            raise ValidationFailed(f"설명은 {CAPTION_MAX:,}자를 넘을 수 없어요.")
        asset.caption = text or None
        self.db.add(asset)
        self.db.commit()
        self.db.refresh(asset)
        return asset

    def relink_photos(self, owner_id: str, session_id: str) -> dict[str, str | None]:
        """사진 연결을 다시 계산해 저장한다. 직접 지정한 연결은 그대로 둔다(요구사항 5.6)."""
        self._session(owner_id, session_id)
        photos = list(
            self.db.exec(
                select(Asset).where(Asset.session_id == session_id, Asset.kind == AssetKind.PHOTO)
            )
        )
        blocks = list(self.db.exec(select(MemoBlock).where(MemoBlock.session_id == session_id)))
        links = link_photos(photos, blocks)
        for photo in photos:
            if photo.linked_block_id != links[photo.id]:
                photo.linked_block_id = links[photo.id]
                self.db.add(photo)
        self.db.commit()
        return links

    def set_link(
        self, owner_id: str, session_id: str, asset_id: str, block_id: str | None
    ) -> Asset:
        """사용자가 사진 연결을 직접 지정한다. 이후 자동 연결이 덮어쓰지 않는다(요구사항 5.6).

        `block_id=None`은 "어느 블록에도 연결하지 않음"을 직접 고른 것이다.
        """
        asset = self.get(owner_id, session_id, asset_id)
        if asset.kind is not AssetKind.PHOTO:
            raise ValidationFailed("연결은 사진에만 지정할 수 있어요.")
        if block_id is not None:
            block = self.db.get(MemoBlock, block_id)
            if block is None or block.session_id != session_id:
                raise ValidationFailed("같은 세션의 메모 블록만 고를 수 있어요.")
        asset.linked_block_id = block_id
        asset.link_manual = True
        self.db.add(asset)
        self.db.commit()
        self.db.refresh(asset)
        return asset

    # ------------------------------------------------------------------ 삭제

    def delete(self, owner_id: str, session_id: str, asset_id: str) -> None:
        """Asset 행, 파생 데이터(`DocChunk`, `TranscriptSegment`), Blob 파일을 함께 지운다(8.6).

        파일을 먼저 지운다. 중간에 실패해도 같은 요청을 다시 보내면 끝낼 수 있다.
        """
        asset = self.get(owner_id, session_id, asset_id)
        if asset.blob_key is not None:
            self.blobs.delete(asset.blob_key)
            if asset.kind is AssetKind.PHOTO:
                self.blobs.delete(asset.blob_key + THUMB_SUFFIX)
        self.db.exec(delete(DocChunk).where(DocChunk.asset_id == asset.id))
        self.db.exec(delete(TranscriptSegment).where(TranscriptSegment.asset_id == asset.id))
        self.db.delete(asset)
        self.db.commit()
