"""초안 API: 만들기, 조회, 문장 검토, 인사이트, 승인, 내보내기(요구사항 19~24)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field

from open_attendee import drafts as svc
from open_attendee.errors import NotFound
from open_attendee.llm import LLMError
from open_attendee.templates import BLOG_TEMPLATE_ID, get_template
from open_attendee.web.deps import Db, Gateway, Owner, Sessions

router = APIRouter(prefix="/api")


class SentencePatch(BaseModel):
    text: str | None = None
    action: str | None = Field(default=None, pattern="^keep_as_opinion$")


class DraftCreate(BaseModel):
    template_id: str = BLOG_TEMPLATE_ID


class InsightBody(BaseModel):
    section_id: str
    text: str


def _error(status: int, code: str, message: str, **extra: Any) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message, **extra}}, status_code=status)


def _body(db: Db, draft: Any, llm_configured: bool | None = None) -> dict[str, Any]:
    view = svc.view_draft(db, draft)
    body: dict[str, Any] = {
        "id": draft.id,
        "status": draft.status.value,
        "approved_at": draft.approved_at.isoformat() if draft.approved_at else None,
        "unverified_count": view.unverified_count,
        "template_name": view.template_name,
        "sections": view.sections,
    }
    if llm_configured is not None:
        body["llm_configured"] = llm_configured
    return body


@router.get("/sessions/{session_id}/draft")
def get_draft(
    session_id: str, owner: Owner, sessions: Sessions, db: Db, gateway: Gateway
) -> dict[str, Any]:
    sessions.get(owner, session_id)
    draft = svc.latest_draft(db, session_id)
    return {
        "draft": _body(db, draft) if draft else None,
        "llm_configured": gateway is not None,
    }


@router.post("/sessions/{session_id}/draft", response_model=None)
def create_draft(
    session_id: str,
    owner: Owner,
    sessions: Sessions,
    db: Db,
    gateway: Gateway,
    body: DraftCreate | None = None,
) -> JSONResponse | dict[str, Any]:
    sessions.get(owner, session_id)
    if gateway is None:
        return _error(
            503, "llm_not_configured", "AI 제공자가 설정되지 않았어요. API 키를 설정해 주세요."
        )
    try:
        template = get_template(db, owner, body.template_id if body else BLOG_TEMPLATE_ID)
    except NotFound:
        return _error(422, "unknown_template", "알 수 없는 템플릿이에요.")
    try:
        draft = svc.generate_draft(db, gateway, session_id, template)
    except svc.NoSources:
        return _error(
            422, "no_sources", "초안을 만들 기록이 없어요. 메모를 쓰거나 자료를 올려 주세요."
        )
    except LLMError as exc:
        return _error(502, "llm_failed", str(exc))
    return {"draft": _body(db, draft), "llm_configured": True}


@router.patch("/drafts/{draft_id}/sentences/{sentence_id}", response_model=None)
def patch_sentence(
    draft_id: str, sentence_id: str, body: SentencePatch, owner: Owner, db: Db
) -> JSONResponse | dict[str, Any]:
    draft = svc.get_draft(db, owner, draft_id)
    try:
        if body.action == "keep_as_opinion":
            svc.keep_as_opinion(db, draft, sentence_id)
        elif body.text is not None:
            svc.edit_sentence(db, draft, sentence_id, body.text)
        else:
            return _error(422, "nothing_to_do", "text나 action 중 하나가 필요해요.")
    except svc.ReviewConflict as exc:
        return _error(409, "conflict", str(exc))
    return _body(db, draft)


@router.delete("/drafts/{draft_id}/sentences/{sentence_id}", response_model=None)
def remove_sentence(
    draft_id: str, sentence_id: str, owner: Owner, db: Db
) -> JSONResponse | dict[str, Any]:
    draft = svc.get_draft(db, owner, draft_id)
    try:
        svc.delete_sentence(db, draft, sentence_id)
    except svc.ReviewConflict as exc:
        return _error(409, "conflict", str(exc))
    return _body(db, draft)


@router.post("/drafts/{draft_id}/insights", response_model=None)
def create_insight(
    draft_id: str, body: InsightBody, owner: Owner, db: Db
) -> JSONResponse | dict[str, Any]:
    draft = svc.get_draft(db, owner, draft_id)
    try:
        svc.add_insight(db, draft, body.section_id, body.text)
    except svc.ReviewConflict as exc:
        return _error(409, "conflict", str(exc))
    return _body(db, draft)


@router.post("/drafts/{draft_id}/approve", response_model=None)
def approve_draft(draft_id: str, owner: Owner, db: Db) -> JSONResponse | dict[str, Any]:
    draft = svc.get_draft(db, owner, draft_id)
    try:
        svc.approve(db, draft)
    except svc.ReviewConflict as exc:
        return _error(409, "conflict", str(exc), sentence_ids=exc.sentence_ids)
    return _body(db, draft)


@router.get("/drafts/{draft_id}/export.md", response_model=None)
def export_draft(draft_id: str, owner: Owner, sessions: Sessions, db: Db) -> Response:
    draft = svc.get_draft(db, owner, draft_id)
    event = sessions.get(owner, draft.session_id)
    try:
        text = svc.export_markdown(db, draft, event.title)
    except svc.ReviewConflict as exc:
        return _error(409, "conflict", str(exc))
    return PlainTextResponse(
        text,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="open-attendee-draft.md"',
            "X-Content-Type-Options": "nosniff",
        },
    )
