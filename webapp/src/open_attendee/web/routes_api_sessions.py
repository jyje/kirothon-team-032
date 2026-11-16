"""세션과 메모 블록 JSON API(요구사항 1, 2)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel, Field

from open_attendee.models import EventSession, MemoBlock
from open_attendee.web.deps import Owner, Sessions

router = APIRouter(prefix="/api")


class SessionCreate(BaseModel):
    title: str = ""
    event_date: date | None = None


class SessionPatch(BaseModel):
    title: str | None = None
    event_date: date | None = Field(default=None)
    retain_audio: bool | None = None


class BlockSave(BaseModel):
    text: str = ""
    position: int | None = None


def _iso(value: datetime) -> str:
    return value.isoformat()


def session_json(event: EventSession) -> dict[str, Any]:
    return {
        "id": event.id,
        "title": event.title,
        "event_date": event.event_date.isoformat() if event.event_date else None,
        "retain_audio": event.retain_audio,
        "created_at": _iso(event.created_at),
        "updated_at": _iso(event.updated_at),
    }


def block_json(block: MemoBlock) -> dict[str, Any]:
    return {
        "id": block.id,
        "position": block.position,
        "text": block.text,
        "revision": block.revision,
        "updated_at": _iso(block.updated_at),
    }


@router.get("/sessions")
def list_sessions(owner: Owner, sessions: Sessions) -> dict[str, Any]:
    return {
        "items": [
            {
                **session_json(item.session),
                "asset_count": item.asset_count,
                "draft_status": item.draft_status,
            }
            for item in sessions.list(owner)
        ]
    }


@router.post("/sessions", status_code=201)
def create_session(body: SessionCreate, owner: Owner, sessions: Sessions) -> dict[str, Any]:
    return session_json(sessions.create(owner, body.title, body.event_date))


@router.get("/sessions/{session_id}")
def get_session(session_id: str, owner: Owner, sessions: Sessions) -> dict[str, Any]:
    event = sessions.get(owner, session_id)
    return {
        **session_json(event),
        "blocks": [block_json(b) for b in sessions.list_blocks(owner, session_id)],
    }


@router.patch("/sessions/{session_id}")
def update_session(
    session_id: str, body: SessionPatch, owner: Owner, sessions: Sessions
) -> dict[str, Any]:
    fields = body.model_fields_set
    kwargs: dict[str, Any] = {}
    if "title" in fields and body.title is not None:
        kwargs["title"] = body.title
    if "event_date" in fields:
        kwargs["event_date"] = body.event_date
    if body.retain_audio is not None:
        kwargs["retain_audio"] = body.retain_audio
    return session_json(sessions.update(owner, session_id, **kwargs))


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(session_id: str, owner: Owner, sessions: Sessions) -> Response:
    sessions.delete(owner, session_id)
    return Response(status_code=204)


@router.put("/sessions/{session_id}/blocks/{block_id}")
def save_block(
    session_id: str, block_id: str, body: BlockSave, owner: Owner, sessions: Sessions
) -> dict[str, Any]:
    return block_json(sessions.save_block(owner, session_id, block_id, body.text, body.position))


@router.delete("/sessions/{session_id}/blocks/{block_id}", status_code=204)
def delete_block(session_id: str, block_id: str, owner: Owner, sessions: Sessions) -> Response:
    sessions.delete_block(owner, session_id, block_id)
    return Response(status_code=204)
