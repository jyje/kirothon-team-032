"""녹음과 음성 메모의 전사 입력, 동의 및 결과 저장."""

from __future__ import annotations

import shutil
from collections.abc import Sequence
from contextlib import closing
from dataclasses import dataclass
from tempfile import TemporaryFile
from typing import BinaryIO, cast

from sqlmodel import Session, col, select

from open_attendee.consent import ConsentGate
from open_attendee.errors import NotFound, ValidationFailed
from open_attendee.models import Asset, AssetKind, AssetStatus, TranscriptSegment
from open_attendee.storage import BlobStore
from open_attendee.transcription import SpeechSegment, Transcriber

AUDIO_KINDS = (AssetKind.RECORDING, AssetKind.VOICE_MEMO)


def get_audio(db: Session, session_id: str, asset_id: str) -> Asset:
    asset = db.get(Asset, asset_id)
    if asset is None or asset.session_id != session_id or asset.kind not in AUDIO_KINDS:
        raise NotFound("음성 자료를 찾을 수 없어요.")
    ConsentGate(db).require_consent(asset)
    return asset


def audio_key(asset: Asset) -> str:
    if asset.blob_key is None:
        raise ValidationFailed("전사할 원본 음성 파일이 없어요.")
    return asset.blob_key


def list_segments(db: Session, asset_id: str) -> Sequence[TranscriptSegment]:
    return db.exec(
        select(TranscriptSegment)
        .where(TranscriptSegment.asset_id == asset_id)
        .order_by(col(TranscriptSegment.start_ms), col(TranscriptSegment.id))
    ).all()


def save_segments(db: Session, asset: Asset, segments: list[SpeechSegment]) -> None:
    # 최초 성공 결과의 ID를 보존한다. 요약과 초안이 이 ID를 출처로 사용한다.
    if asset.status in (AssetStatus.READY, AssetStatus.ORIGINAL_DELETED):
        return
    db.add_all(
        TranscriptSegment(asset_id=asset.id, start_ms=s.start_ms, end_ms=s.end_ms, text=s.text)
        for s in segments
    )
    asset.status = AssetStatus.READY
    db.add(asset)


@dataclass(frozen=True)
class TranscriptionRunner:
    blobs: BlobStore
    transcriber: Transcriber

    def run(self, key: str) -> list[SpeechSegment]:
        with closing(self.blobs.open(key)) as audio:
            if audio.seekable():
                return list(self.transcriber.transcribe(audio))
            # 일부 컨테이너는 탐색이 필요하다. 원격 객체만 임시 파일에 복사한다.
            with TemporaryFile() as temporary:
                shutil.copyfileobj(audio, temporary)
                temporary.seek(0)
                return list(self.transcriber.transcribe(cast(BinaryIO, temporary)))
