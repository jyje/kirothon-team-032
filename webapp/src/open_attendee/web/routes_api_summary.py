"""출처가 붙은 요약 API(요구사항 16.3, 18)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from open_attendee.llm import LLMError
from open_attendee.models import LiveSummary
from open_attendee.pipeline.summary import NoSources, generate_summary, latest_summary
from open_attendee.web.deps import Db, Gateway, Owner, Sessions

router = APIRouter(prefix="/api")


def _body(summary: LiveSummary | None) -> dict[str, Any] | None:
    if summary is None:
        return None
    return {
        "id": summary.id,
        "created_at": summary.created_at.isoformat(),
        "bullets": [
            {
                "text": b["text"],
                "sources": [
                    {"kind": s["kind"], "locator": s["locator"], "target_id": s["target_id"]}
                    for s in b["sources"]
                ],
            }
            for b in summary.bullets
        ],
    }


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


@router.get("/sessions/{session_id}/summary")
def get_summary(
    session_id: str, owner: Owner, sessions: Sessions, db: Db, gateway: Gateway
) -> dict[str, Any]:
    sessions.get(owner, session_id)  # 소유자 확인(없으면 404)
    return {"summary": _body(latest_summary(db, session_id)), "llm_configured": gateway is not None}


@router.post("/sessions/{session_id}/summary", response_model=None)
def create_summary(
    session_id: str, owner: Owner, sessions: Sessions, db: Db, gateway: Gateway
) -> JSONResponse | dict[str, Any]:
    sessions.get(owner, session_id)
    if gateway is None:
        return _error(
            503, "llm_not_configured", "AI 제공자가 설정되지 않았어요. API 키를 설정해 주세요."
        )
    try:
        result = generate_summary(db, gateway, session_id)
    except NoSources:
        return _error(422, "no_sources", "요약할 기록이 없어요. 메모를 쓰거나 자료를 올려 주세요.")
    except LLMError as exc:
        return _error(502, "llm_failed", str(exc))
    return {
        "summary": _body(result.summary),
        "llm_configured": True,
        "dropped_bullets": result.dropped_bullets,
        "truncated": result.truncated,
    }
