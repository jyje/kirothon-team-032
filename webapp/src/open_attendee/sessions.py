"""`SessionService`: 행사 세션과 메모 블록(요구사항 1, 2).

모든 조회와 변경은 `owner_id`로 한정한다(요구사항 25.7). 다른 소유자의 세션은 "없음"과 같게 보인다.
각 공개 메서드는 하나의 작업 단위라서 끝날 때 커밋한다.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from typing import Final

from sqlalchemy import delete, func, update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from open_attendee.errors import NotFound, ValidationFailed
from open_attendee.models import (
    Asset,
    ConsentRecord,
    DocChunk,
    Draft,
    EventSession,
    Fact,
    Job,
    LiveSummary,
    MemoBlock,
    Sentence,
    TranscriptSegment,
    utcnow,
)
from open_attendee.storage import BlobStore

TITLE_MIN: Final = 1
TITLE_MAX: Final = 200
BLOCK_TEXT_MAX: Final = 10_000


class _Unset:
    """`None`(값을 비움)과 "바꾸지 않음"을 구분하는 표시."""

    def __repr__(self) -> str:
        return "UNSET"


UNSET: Final = _Unset()


@dataclass(frozen=True)
class SessionListItem:
    session: EventSession
    asset_count: int
    draft_status: str | None  # 가장 최근 초안의 상태. 초안이 없으면 None


def validate_title(title: str) -> str:
    """앞뒤 공백을 뺀 제목이 1~200자여야 한다. 정리한 제목을 돌려준다."""
    cleaned = title.strip() if isinstance(title, str) else ""
    if not TITLE_MIN <= len(cleaned) <= TITLE_MAX:
        raise ValidationFailed(f"세션 제목은 {TITLE_MIN}~{TITLE_MAX}자여야 해요.")
    return cleaned


def normalize_block_id(block_id: str) -> str:
    """클라이언트가 만든 UUID를 소문자 하이픈 형식으로 맞춘다. UUID가 아니면 거부한다."""
    try:
        return str(uuid.UUID(block_id))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValidationFailed("메모 블록 ID는 UUID여야 해요.") from exc


class SessionService:
    def __init__(self, db: Session, blobs: BlobStore) -> None:
        self.db = db
        self.blobs = blobs

    # ------------------------------------------------------------------ 세션

    def create(self, owner_id: str, title: str, event_date: date | None = None) -> EventSession:
        event = EventSession(owner_id=owner_id, title=validate_title(title), event_date=event_date)
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return event

    def get(self, owner_id: str, session_id: str) -> EventSession:
        event = self.db.exec(
            select(EventSession).where(
                EventSession.id == session_id, EventSession.owner_id == owner_id
            )
        ).one_or_none()
        if event is None:
            raise NotFound("세션을 찾을 수 없어요.")
        return event

    def update(
        self,
        owner_id: str,
        session_id: str,
        *,
        title: str | _Unset = UNSET,
        event_date: date | _Unset | None = UNSET,
        retain_audio: bool | _Unset = UNSET,
    ) -> EventSession:
        event = self.get(owner_id, session_id)
        if not isinstance(title, _Unset):
            event.title = validate_title(title)
        if not isinstance(event_date, _Unset):
            event.event_date = event_date
        if not isinstance(retain_audio, _Unset):
            event.retain_audio = retain_audio
        event.updated_at = utcnow()
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return event

    def delete(self, owner_id: str, session_id: str) -> None:
        """세션과 속한 모든 DB 행, Blob 파일을 지운다(요구사항 1.5).

        파일을 먼저 지운다. 지우다 실패하면 DB가 그대로라서 같은 요청을 다시 보낼 수 있다.
        """
        event = self.get(owner_id, session_id)
        self.blobs.delete_prefix(f"{owner_id}/{session_id}")

        asset_ids = select(Asset.id).where(Asset.session_id == session_id)
        draft_ids = select(Draft.id).where(Draft.session_id == session_id)
        self.db.exec(delete(DocChunk).where(DocChunk.asset_id.in_(asset_ids)))
        self.db.exec(delete(TranscriptSegment).where(TranscriptSegment.asset_id.in_(asset_ids)))
        self.db.exec(delete(Fact).where(Fact.draft_id.in_(draft_ids)))
        self.db.exec(delete(Sentence).where(Sentence.draft_id.in_(draft_ids)))
        for table in (Asset, ConsentRecord, MemoBlock, Draft, LiveSummary, Job):
            self.db.exec(delete(table).where(table.session_id == session_id))
        self.db.delete(event)
        self.db.commit()

    def list(self, owner_id: str) -> list[SessionListItem]:
        """최근 행사부터. 자료 수와 가장 최근 초안의 상태를 함께 돌려준다."""
        sessions = list(
            self.db.exec(
                select(EventSession)
                .where(EventSession.owner_id == owner_id)
                .order_by(
                    EventSession.event_date.desc().nulls_last(), EventSession.created_at.desc()
                )
            )
        )
        if not sessions:
            return []
        ids = [s.id for s in sessions]
        counts = {
            session_id: count
            for session_id, count in self.db.exec(
                select(Asset.session_id, func.count())
                .where(Asset.session_id.in_(ids))
                .group_by(Asset.session_id)
            )
        }
        draft_status: dict[str, str] = {}
        drafts = self.db.exec(
            select(Draft).where(Draft.session_id.in_(ids)).order_by(Draft.created_at)
        )
        for draft in drafts:  # 오래된 것부터 덮어써서 마지막에 가장 최근 초안이 남는다
            draft_status[draft.session_id] = str(draft.status)
        return [SessionListItem(s, counts.get(s.id, 0), draft_status.get(s.id)) for s in sessions]

    # ------------------------------------------------------------------ 메모 블록

    def list_blocks(self, owner_id: str, session_id: str) -> list[MemoBlock]:
        self.get(owner_id, session_id)
        return list(
            self.db.exec(
                select(MemoBlock)
                .where(MemoBlock.session_id == session_id)
                .order_by(MemoBlock.position, MemoBlock.created_at)
            )
        )

    def save_block(
        self,
        owner_id: str,
        session_id: str,
        block_id: str,
        text: str,
        position: int | None = None,
    ) -> MemoBlock:
        """블록을 저장한다. 처음이면 `revision=1`, 있으면 정확히 1 올린다(요구사항 2.1, 2.2)."""
        block_id = normalize_block_id(block_id)
        if not isinstance(text, str) or len(text) > BLOCK_TEXT_MAX:
            raise ValidationFailed(f"메모는 {BLOCK_TEXT_MAX:,}자를 넘을 수 없어요.")
        self.get(owner_id, session_id)

        existing = self.db.get(MemoBlock, block_id)
        if existing is not None and existing.session_id != session_id:
            raise ValidationFailed("이 블록 ID는 이미 다른 세션에서 쓰고 있어요.")
        if existing is None:
            now = utcnow()
            block = MemoBlock(
                id=block_id,
                session_id=session_id,
                position=position if position is not None else self._next_position(session_id),
                text=text,
                revision=1,
                created_at=now,
                updated_at=now,
            )
            self.db.add(block)
            try:
                self.db.commit()
            except IntegrityError:
                # 같은 ID로 동시에 처음 저장한 요청이 먼저 들어갔다. 다시 저장으로 처리한다.
                self.db.rollback()
            else:
                self.db.refresh(block)
                return block
        return self._bump_block(session_id, block_id, text, position)

    def _bump_block(
        self, session_id: str, block_id: str, text: str, position: int | None
    ) -> MemoBlock:
        values: dict[str, object] = {
            "text": text,
            # 읽고 쓰는 사이에 다른 요청이 끼어도 정확히 1씩 오르도록 DB에서 더한다.
            "revision": MemoBlock.revision + 1,
            "updated_at": utcnow(),
        }
        if position is not None:
            values["position"] = position
        result = self.db.exec(
            update(MemoBlock)
            .where(MemoBlock.id == block_id, MemoBlock.session_id == session_id)
            .values(**values)
        )
        self.db.commit()
        if result.rowcount != 1:
            raise NotFound("메모 블록을 찾을 수 없어요.")
        block = self.db.get(MemoBlock, block_id)
        if block is None:
            raise NotFound("메모 블록을 찾을 수 없어요.")
        self.db.refresh(block)
        return block

    def delete_block(self, owner_id: str, session_id: str, block_id: str) -> None:
        block_id = normalize_block_id(block_id)
        self.get(owner_id, session_id)
        block = self.db.get(MemoBlock, block_id)
        if block is None or block.session_id != session_id:
            raise NotFound("메모 블록을 찾을 수 없어요.")
        # 이 블록에 연결된 사진은 연결만 풀고 사진은 남긴다.
        self.db.exec(
            update(Asset)
            .where(Asset.session_id == session_id, Asset.linked_block_id == block_id)
            .values(linked_block_id=None, link_manual=False)
        )
        self.db.delete(block)
        self.db.commit()

    def _next_position(self, session_id: str) -> int:
        top = self.db.exec(
            select(func.max(MemoBlock.position)).where(MemoBlock.session_id == session_id)
        ).one()
        return 0 if top is None else top + 1
