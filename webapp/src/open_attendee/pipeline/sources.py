"""출처 대응표(요구사항 18).

프롬프트에는 `S1`, `S2` 같은 짧은 라벨과 출처 텍스트만 넣고, 라벨의 실제 대상(`SourceRef`)은
서버에만 둔다. LLM이 대응표에 없는 라벨을 지어내도 저장되지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlmodel import Session, select

from open_attendee.models import (
    Asset,
    AssetKind,
    DocChunk,
    MemoBlock,
    SourceKind,
    SourceRef,
)

# 한 번에 LLM에 보내는 출처 텍스트의 한도(요구사항 18.7). 넘으면 앞에서부터 담고 잘렸다고 알린다.
MAX_SOURCE_CHARS = 24_000
MAX_ITEM_CHARS = 4_000


@dataclass(frozen=True)
class SourceItem:
    label: str
    ref: SourceRef
    text: str


@dataclass(frozen=True)
class SourceMap:
    items: list[SourceItem]
    truncated: bool

    def get(self, label: str) -> SourceItem | None:
        return next((i for i in self.items if i.label == label), None)

    def __len__(self) -> int:
        return len(self.items)


def build_source_map(
    db: Session, session_id: str, *, citations: list[SourceRef] | None = None
) -> SourceMap:
    """비어 있지 않은 메모, 발표자료와 참고자료 조각, 설명이 있는 사진으로 대응표를 만든다."""
    raw: list[tuple[SourceRef, str]] = []

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
            where = f"{asset.display_name} {chunk.page}쪽"
            ref = SourceRef(kind=kind, target_id=chunk.id, locator=where)
            raw.append((ref, chunk.text.strip()))

    for asset in assets:
        if asset.kind is AssetKind.PHOTO and (asset.caption or "").strip():
            ref = SourceRef(kind=SourceKind.PHOTO, target_id=asset.id, locator=asset.display_name)
            raw.append((ref, f"사진 설명: {asset.caption.strip()}"))  # type: ignore[union-attr]

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
        items.append(SourceItem(label=f"S{len(items) + 1}", ref=ref, text=text))
    return SourceMap(items=items, truncated=truncated)


def render_sources(source_map: SourceMap) -> str:
    """프롬프트에 넣을 출처 블록. 구분자를 깨는 글자는 바꿔 출처 글이 지시가 되지 못하게 한다."""
    parts = []
    for item in source_map.items:
        safe = item.text.replace("</source", "<\\/source").replace("<source", "<\\source")
        parts.append(f'<source id="{item.label}">\n{safe}\n</source>')
    return "\n".join(parts)
