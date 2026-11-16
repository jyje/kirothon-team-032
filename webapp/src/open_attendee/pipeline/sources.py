"""출처 대응표(요구사항 18).

프롬프트에는 `S1`, `S2` 같은 짧은 라벨과 출처 텍스트만 넣고, 라벨의 실제 대상(`SourceRef`)은
서버에만 둔다. LLM이 대응표에 없는 라벨을 지어내도 저장되지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlmodel import Session, col, select

from open_attendee.consent import is_valid_consent, require_result_consent
from open_attendee.models import (
    Asset,
    AssetKind,
    ConsentRecord,
    DocChunk,
    MemoBlock,
    SourceKind,
    SourceRef,
    TranscriptSegment,
)
from open_attendee.processors.docs import PPTX_MIME
from open_attendee.transcript_jobs import AUDIO_KINDS

# 한 번에 LLM에 보내는 출처 텍스트의 한도(요구사항 18.7). 넘으면 앞에서부터 담고 잘렸다고 알린다.
MAX_SOURCE_CHARS = 24_000
MAX_ITEM_CHARS = 4_000


@dataclass(frozen=True)
class SourceItem:
    label: str
    ref: SourceRef
    text: str
    consent_id: str | None = None


@dataclass(frozen=True)
class SourceMap:
    items: list[SourceItem]
    truncated: bool

    def get(self, label: str) -> SourceItem | None:
        return next((i for i in self.items if i.label == label), None)

    @property
    def consent_ids(self) -> list[str]:
        return sorted({item.consent_id for item in self.items if item.consent_id is not None})

    def lock_consent(self, db: Session, session_id: str) -> None:
        consent_ids = self.consent_ids
        if consent_ids:
            db.rollback()
            db.connection().exec_driver_sql("BEGIN IMMEDIATE")
            require_result_consent(db, session_id, consent_ids)

    def __len__(self) -> int:
        return len(self.items)


def build_source_map(
    db: Session, session_id: str, *, citations: list[SourceRef] | None = None
) -> SourceMap:
    """행사의 비어 있지 않은 메모, 첨부 자료와 유효한 전사로 대응표를 만든다."""
    raw: list[tuple[SourceRef, str]] = []
    transcript_consents: dict[str, str] = {}

    blocks = db.exec(
        select(MemoBlock).where(MemoBlock.session_id == session_id).order_by(MemoBlock.position)
    ).all()
    for number, block in enumerate(blocks, start=1):
        if block.text.strip():
            ref = SourceRef(
                kind=SourceKind.MEMO,
                target_id=block.id,
                revision=block.revision,
                locator=f"메모 {number}번째 블록",
            )
            raw.append((ref, block.text.strip()))

    assets = db.exec(select(Asset).where(Asset.session_id == session_id)).all()
    by_id = {a.id: a for a in assets}
    doc_assets = [a for a in assets if a.kind in (AssetKind.SLIDES, AssetKind.REFERENCE)]
    if doc_assets:
        chunks = db.exec(
            select(DocChunk)
            .where(DocChunk.asset_id.in_([a.id for a in doc_assets]))  # type: ignore[attr-defined]
            .order_by(DocChunk.asset_id, DocChunk.page, DocChunk.part)
        ).all()
        for chunk in chunks:
            asset = by_id[chunk.asset_id]
            if not chunk.text.strip():
                continue
            kind = SourceKind.DOC if asset.kind is AssetKind.SLIDES else SourceKind.REFERENCE
            page = f"슬라이드 {chunk.page}" if asset.mime == PPTX_MIME else f"{chunk.page}쪽"
            where = f"{asset.display_name} {page}"
            ref = SourceRef(kind=kind, target_id=chunk.id, locator=where)
            raw.append((ref, chunk.text.strip()))

    for asset in assets:
        if asset.kind is AssetKind.PHOTO and (asset.caption or "").strip():
            ref = SourceRef(kind=SourceKind.PHOTO, target_id=asset.id, locator=asset.display_name)
            raw.append((ref, f"사진 설명: {asset.caption.strip()}"))  # type: ignore[union-attr]

    audio_assets = [asset for asset in assets if asset.kind in AUDIO_KINDS]
    if audio_assets:
        valid_ids = {
            record.id
            for record in db.exec(
                select(ConsentRecord).where(ConsentRecord.session_id == session_id)
            )
            if is_valid_consent(record, session_id)
        }
        allowed = [
            asset.id
            for asset in audio_assets
            if (asset.kind is AssetKind.VOICE_MEMO and asset.solo_voice)
            or asset.consent_id in valid_ids
        ]
        if allowed:
            transcripts = db.exec(
                select(TranscriptSegment)
                .where(col(TranscriptSegment.asset_id).in_(allowed))
                .order_by(col(TranscriptSegment.asset_id), col(TranscriptSegment.start_ms))
            )
            for segment in transcripts:
                if segment.text.strip():
                    asset = by_id[segment.asset_id]
                    if not (asset.kind is AssetKind.VOICE_MEMO and asset.solo_voice):
                        assert asset.consent_id is not None  # allowed에서 유효한 동의를 확인했다
                        transcript_consents[segment.id] = asset.consent_id
                    name = asset.display_name
                    locator = f"{name} {_timestamp(segment.start_ms)}~{_timestamp(segment.end_ms)}"
                    raw.append(
                        (
                            SourceRef(
                                kind=SourceKind.TRANSCRIPT, target_id=segment.id, locator=locator
                            ),
                            segment.text.strip(),
                        )
                    )

    items: list[SourceItem] = []
    used = 0
    truncated = False
    cited = {(ref.kind, ref.target_id, ref.revision) for ref in citations or []}
    for ref, text in raw:
        if citations is not None and (ref.kind, ref.target_id, ref.revision) not in cited:
            continue
        text = text[:MAX_ITEM_CHARS]
        if used + len(text) > MAX_SOURCE_CHARS:
            truncated = True
            break
        used += len(text)
        items.append(
            SourceItem(
                label=f"S{len(items) + 1}",
                ref=ref,
                text=text,
                consent_id=transcript_consents.get(ref.target_id)
                if ref.kind is SourceKind.TRANSCRIPT
                else None,
            )
        )
    return SourceMap(items=items, truncated=truncated)


def _timestamp(milliseconds: int) -> str:
    minutes, seconds = divmod(milliseconds // 1000, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}.{milliseconds % 1000:03}"


def render_sources(source_map: SourceMap) -> str:
    """프롬프트에 넣을 출처 블록. 구분자를 깨는 글자는 바꿔 출처 글이 지시가 되지 못하게 한다."""
    parts = []
    for item in source_map.items:
        safe = item.text.replace("</source", "<\\/source").replace("<source", "<\\source")
        parts.append(f'<source id="{item.label}">\n{safe}\n</source>')
    return "\n".join(parts)
