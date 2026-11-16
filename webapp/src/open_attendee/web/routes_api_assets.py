"""자료 업로드, 삭제, 설명과 사진 연결, 파일 응답 JSON API(요구사항 3.9, 5.6, 6.3, 8.5, 11.2)."""

from __future__ import annotations

import string
from collections.abc import Iterator
from typing import Annotated, BinaryIO
from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from open_attendee import transcript_jobs
from open_attendee.assets import COUNT_LIMITS, SIZE_LIMITS, PhotoRevisionChanged
from open_attendee.errors import ValidationFailed
from open_attendee.models import Asset, AssetKind
from open_attendee.processors.face_detection import MAX_REGIONS, PhotoRegion
from open_attendee.web.deps import AppSettings, Assets, Db, Owner, Sessions

router = APIRouter(prefix="/api")

_CHUNK = 1024 * 1024
_FILENAME_SAFE = frozenset(string.ascii_letters + string.digits + "._-")


def recording_enabled(settings: AppSettings) -> bool:
    """녹음 메뉴와 버튼을 보여 줄지. 플래그가 꺼져 있거나 전사기가 없으면 숨긴다(요구사항 11.2)."""
    return settings.feature_recording and settings.transcriber != "none"


def _asset_body(asset: Asset) -> dict[str, object]:
    return {
        "id": asset.id,
        "kind": asset.kind.value,
        "display_name": asset.display_name,
        "mime": asset.mime,
        "size_bytes": asset.size_bytes,
        "page_count": asset.page_count,
        "status": asset.status.value,
        "caption": asset.caption,
        "linked_block_id": asset.linked_block_id,
        "link_manual": asset.link_manual,
        "faces_blurred": asset.faces_blurred,
        "face_check_confirmed": asset.face_check_confirmed,
    }


def _content_disposition(filename: str) -> str:
    """`attachment`로 내려받게 한다. 이름은 ASCII 대체 이름과 UTF-8 이름을 함께 보낸다."""
    fallback = "".join(
        ch if (ch.isascii() and ch.isalnum()) or ch in "._-" else "_" for ch in filename
    )
    return f"attachment; filename=\"{fallback or 'file'}\"; filename*=UTF-8''{quote(filename)}"


def _stream(handle: BinaryIO) -> Iterator[bytes]:
    try:
        while chunk := handle.read(_CHUNK):
            yield chunk
    finally:
        handle.close()


# ---------------------------------------------------------------------------- 목록과 업로드


@router.get("/sessions/{session_id}/assets")
def list_assets(
    session_id: str, owner: Owner, assets: Assets, settings: AppSettings, request: Request
) -> dict[str, object]:
    assets.relink_photos(owner, session_id)  # 메모가 늘거나 줄어도 자동 연결을 최신으로 맞춘다
    counts = assets.chunk_counts(session_id)
    return {
        "items": [
            {**_asset_body(a), "chunk_count": counts.get(a.id, 0)}
            for a in assets.list(owner, session_id)
        ],
        "limits": {kind.value: limit for kind, limit in COUNT_LIMITS.items()},
        "recording_enabled": recording_enabled(settings),
        "transcription_enabled": request.app.state.transcriber is not None,
        "recording_max_bytes": SIZE_LIMITS[AssetKind.RECORDING],
    }


@router.post("/sessions/{session_id}/assets", status_code=201)
def upload_asset(
    session_id: str,
    owner: Owner,
    assets: Assets,
    kind: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
    consent_id: Annotated[str, Form()] = "",
    solo_voice: Annotated[bool, Form()] = False,
) -> dict[str, object]:
    try:
        asset_kind = AssetKind(kind)
    except ValueError as exc:
        raise ValidationFailed("자료 종류를 알 수 없어요.") from exc
    created = assets.store_upload(
        owner,
        session_id,
        asset_kind,
        file.filename or "",
        file.file,
        consent_id=consent_id.strip() or None,
        solo_voice=solo_voice,
    )
    if created.kind is AssetKind.PHOTO:
        assets.relink_photos(owner, session_id)  # 업로드 직후 연결을 계산한다
        created = assets.get(owner, session_id, created.id)
    return _asset_body(created)


class PhotoReview(BaseModel):
    revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    regions: list[PhotoRegion] = Field(max_length=MAX_REGIONS)


@router.get("/sessions/{session_id}/assets/{asset_id}/face-review")
def photo_candidates(
    session_id: str,
    asset_id: str,
    owner: Owner,
    assets: Assets,
) -> dict[str, object]:
    return assets.review_photo(owner, session_id, asset_id)


@router.put("/sessions/{session_id}/assets/{asset_id}/face-review")
def save_photo_review(
    session_id: str,
    asset_id: str,
    body: PhotoReview,
    owner: Owner,
    assets: Assets,
) -> dict[str, object]:
    try:
        return _asset_body(
            assets.save_photo_review(owner, session_id, asset_id, body.revision, body.regions)
        )
    except PhotoRevisionChanged as exc:
        raise HTTPException(409, "사진이 변경됐어요. 검토를 다시 열어 주세요.") from exc


@router.get("/sessions/{session_id}/assets/{asset_id}/transcript")
def read_transcript(
    session_id: str, asset_id: str, owner: Owner, sessions: Sessions, db: Db
) -> dict[str, object]:
    sessions.get(owner, session_id)
    asset = transcript_jobs.get_audio(db, session_id, asset_id)
    return {
        "completed": asset.status in transcript_jobs.TRANSCRIBED_STATUSES,
        "asset_status": asset.status.value,
        "segments": [
            {"start_ms": s.start_ms, "end_ms": s.end_ms, "text": s.text}
            for s in transcript_jobs.list_segments(db, asset_id)
        ],
    }


@router.delete("/sessions/{session_id}/assets/{asset_id}", status_code=204)
def delete_asset(session_id: str, asset_id: str, owner: Owner, assets: Assets) -> Response:
    assets.delete(owner, session_id, asset_id)
    return Response(status_code=204)


# ---------------------------------------------------------------------------- 설명과 연결


@router.put("/sessions/{session_id}/assets/{asset_id}/caption")
def save_caption(
    session_id: str,
    asset_id: str,
    owner: Owner,
    assets: Assets,
    caption: Annotated[str, Form()] = "",
) -> dict[str, object]:
    return _asset_body(assets.set_caption(owner, session_id, asset_id, caption))


@router.put("/sessions/{session_id}/assets/{asset_id}/link")
def save_link(
    session_id: str,
    asset_id: str,
    owner: Owner,
    assets: Assets,
    block_id: Annotated[str, Form()] = "",
) -> dict[str, object]:
    return _asset_body(assets.set_link(owner, session_id, asset_id, block_id.strip() or None))


# ---------------------------------------------------------------------------- 파일 응답


def _file_response(
    assets: Assets, owner: str, session_id: str, asset_id: str, *, thumbnail: bool
) -> Response:
    opened = assets.open_file(owner, session_id, asset_id, thumbnail=thumbnail)
    asset = opened.asset
    name = f"thumbnail-{asset.id}.jpg" if thumbnail else asset.display_name
    headers = {
        "Content-Disposition": _content_disposition(name),  # 브라우저가 열지 않고 내려받게 한다
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": (
            "private, no-store"
            if asset.kind is AssetKind.PHOTO or asset.kind in transcript_jobs.AUDIO_KINDS
            else "private, max-age=3600"
        ),
    }
    media_type = "image/jpeg" if thumbnail else asset.mime
    if not thumbnail:
        headers["Content-Length"] = str(asset.size_bytes)
    return StreamingResponse(_stream(opened.stream), media_type=media_type, headers=headers)


@router.get("/sessions/{session_id}/assets/{asset_id}/file")
def download_asset(session_id: str, asset_id: str, owner: Owner, assets: Assets) -> Response:
    return _file_response(assets, owner, session_id, asset_id, thumbnail=False)


@router.get("/sessions/{session_id}/assets/{asset_id}/thumbnail")
def download_thumbnail(session_id: str, asset_id: str, owner: Owner, assets: Assets) -> Response:
    return _file_response(assets, owner, session_id, asset_id, thumbnail=True)
