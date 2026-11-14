"""세션 목록, 기록 화면, 메모 블록 저장 라우트(요구사항 1, 2)."""

from __future__ import annotations

import html
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from open_attendee.errors import ValidationFailed
from open_attendee.models import DraftStatus
from open_attendee.web.deps import Owner, Sessions, is_htmx, templates, wants_json

router = APIRouter()

DRAFT_STATUS_LABELS = {
    DraftStatus.GENERATING.value: "만드는 중",
    DraftStatus.IN_REVIEW.value: "검토 중",
    DraftStatus.APPROVED.value: "승인됨",
    DraftStatus.FAILED.value: "만들지 못함",
}


def parse_date(value: str) -> date | None:
    """폼의 날짜 칸. 비어 있으면 날짜 없음, 형식이 틀리면 검증 오류."""
    value = value.strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValidationFailed("날짜는 YYYY-MM-DD 형식이어야 해요.") from exc


def error_fragment(message: str) -> HTMLResponse:
    """HTMX 요청에 돌려주는 짧은 오류 조각. `app.js`가 422도 화면에 끼워 넣는다."""
    return HTMLResponse(
        f'<span class="alert alert--inline" role="alert">{html.escape(message)}</span>',
        status_code=422,
    )


@router.get("/")
def root() -> Response:
    return RedirectResponse("/sessions", status_code=303)


def _list_page(
    request: Request,
    sessions: Sessions,
    owner: str,
    *,
    error: str | None = None,
    form_title: str = "",
    form_date: str = "",
    status_code: int = 200,
) -> Response:
    return templates.TemplateResponse(
        request,
        "sessions_list.html",
        {
            "items": sessions.list(owner),
            "status_labels": DRAFT_STATUS_LABELS,
            "error": error,
            "form_title": form_title,
            "form_date": form_date,
        },
        status_code=status_code,
    )


@router.get("/sessions")
def list_sessions(request: Request, owner: Owner, sessions: Sessions) -> Response:
    return _list_page(request, sessions, owner)


@router.post("/sessions")
def create_session(
    request: Request,
    owner: Owner,
    sessions: Sessions,
    title: Annotated[str, Form()] = "",
    event_date: Annotated[str, Form()] = "",
) -> Response:
    try:
        created = sessions.create(owner, title, parse_date(event_date))
    except ValidationFailed as exc:
        return _list_page(
            request,
            sessions,
            owner,
            error=str(exc),
            form_title=title,
            form_date=event_date,
            status_code=422,
        )
    return RedirectResponse(f"/sessions/{created.id}", status_code=303)


@router.get("/sessions/{session_id}")
def show_session(request: Request, session_id: str, owner: Owner, sessions: Sessions) -> Response:
    event = sessions.get(owner, session_id)
    return templates.TemplateResponse(
        request,
        "session_detail.html",
        {"event": event, "blocks": sessions.list_blocks(owner, session_id)},
    )


@router.patch("/sessions/{session_id}")
def update_session(
    request: Request,
    session_id: str,
    owner: Owner,
    sessions: Sessions,
    title: Annotated[str, Form()] = "",
    event_date: Annotated[str, Form()] = "",
) -> Response:
    try:
        updated = sessions.update(owner, session_id, title=title, event_date=parse_date(event_date))
    except ValidationFailed as exc:
        if wants_json(request) or not is_htmx(request):
            raise
        return error_fragment(str(exc))
    if wants_json(request):
        return JSONResponse({"id": updated.id, "title": updated.title})
    return HTMLResponse('<span class="hint" role="status">저장했어요</span>')


@router.delete("/sessions/{session_id}")
def delete_session(request: Request, session_id: str, owner: Owner, sessions: Sessions) -> Response:
    sessions.delete(owner, session_id)
    response = Response(status_code=204)
    if is_htmx(request):
        response.headers["HX-Redirect"] = "/sessions"
    return response


@router.put("/sessions/{session_id}/blocks/{block_id}")
def save_block(
    request: Request,
    session_id: str,
    block_id: str,
    owner: Owner,
    sessions: Sessions,
    text: Annotated[str, Form()] = "",
    position: Annotated[int | None, Form()] = None,
) -> Response:
    try:
        block = sessions.save_block(owner, session_id, block_id, text, position)
    except ValidationFailed as exc:
        if wants_json(request) or not is_htmx(request):
            raise
        return error_fragment(str(exc))
    if wants_json(request):
        return JSONResponse({"id": block.id, "revision": block.revision})
    return HTMLResponse(
        f'<span class="hint" role="status" data-revision="{block.revision}">'
        f"저장했어요 · 수정 {block.revision}번째</span>"
    )


@router.delete("/sessions/{session_id}/blocks/{block_id}")
def delete_block(session_id: str, block_id: str, owner: Owner, sessions: Sessions) -> Response:
    sessions.delete_block(owner, session_id, block_id)
    # HTMX가 `outerHTML`로 바꿀 빈 본문. 204는 바꾸지 않으므로 200을 쓴다.
    return HTMLResponse("")
