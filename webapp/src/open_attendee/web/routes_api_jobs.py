"""AI 작업 등록, 진행 상태 및 상태 변경 스트림."""

from __future__ import annotations

import json
from asyncio import sleep
from collections.abc import AsyncIterator
from time import monotonic
from typing import Any, Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, model_validator
from sqlalchemy import Engine
from sqlmodel import Session
from starlette.concurrency import run_in_threadpool

from open_attendee import jobs, templates
from open_attendee.errors import NotFound
from open_attendee.models import Job, JobKind, JobStatus
from open_attendee.web.deps import Db, Owner, Sessions, get_gateway

router = APIRouter(prefix="/api")
QueueKind = Literal["summary", "draft", "transcribe"]


class JobRequest(BaseModel):
    kind: QueueKind
    template_id: str | None = None
    asset_id: str | None = None

    @model_validator(mode="after")
    def validate_asset(self) -> JobRequest:
        if self.kind == "transcribe" and not self.asset_id:
            raise ValueError("전사할 음성 자료를 선택해 주세요.")
        return self


def _body(job: Job) -> dict[str, Any]:
    return {
        "id": job.id,
        "kind": job.kind.value,
        "status": job.status.value,
        "attempts": job.attempts,
        "asset_id": job.payload.get("asset_id"),
        "result_id": job.payload.get("result_id"),
        "dropped_bullets": int(job.payload.get("dropped_bullets", "0")),
        "truncated": job.payload.get("truncated") == "1",
        "error_code": job.last_error if job.status is JobStatus.FAILED else None,
    }


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


@router.post("/sessions/{session_id}/jobs")
def create_job(
    session_id: str,
    body: JobRequest,
    owner: Owner,
    sessions: Sessions,
    db: Db,
    request: Request,
) -> JSONResponse:
    sessions.get(owner, session_id)
    kind = JobKind(body.kind)
    payload: dict[str, str] = {}
    if kind is JobKind.TRANSCRIBE:
        if request.app.state.transcriber is None:
            return _error(503, "transcriber_not_configured", "전사기가 설정되지 않았어요.")
        payload["asset_id"] = body.asset_id or ""
    elif get_gateway(request) is None:
        return _error(503, "llm_not_configured", "AI 제공자가 설정되지 않았어요.")
    if kind is JobKind.DRAFT:
        try:
            template = templates.get_template(
                db, owner, body.template_id or templates.BLOG_TEMPLATE_ID
            )
        except NotFound:
            return _error(422, "unknown_template", "알 수 없는 템플릿이에요.")
        payload["template"] = template.model_dump_json()
    try:
        job, created = jobs.enqueue(db, session_id, owner, kind, payload)
    except jobs.JobConflict:
        message = (
            "이 행사의 다른 전사가 진행 중이에요."
            if kind is JobKind.TRANSCRIBE
            else "이 행사의 다른 초안 작업이 진행 중이에요."
        )
        return _error(409, "job_conflict", message)
    return JSONResponse(_body(job), status_code=202 if created else 200)


@router.get("/sessions/{session_id}/jobs")
def latest_job(
    session_id: str, kind: QueueKind, owner: Owner, db: Db, asset_id: str | None = None
) -> dict[str, Any]:
    job = jobs.latest_job(
        db, session_id, owner, JobKind(kind), asset_id if kind == "transcribe" else None
    )
    return {"job": _body(job) if job else None}


@router.get("/jobs/{job_id}")
def get_job(job_id: str, owner: Owner, db: Db) -> dict[str, Any]:
    return _body(jobs.get_job(db, job_id, owner))


def _read_job(engine: Engine, job_id: str, owner: str) -> dict[str, Any]:
    with Session(engine) as db:
        return _body(jobs.get_job(db, job_id, owner))


@router.get("/jobs/{job_id}/events")
def job_events(job_id: str, owner: Owner, request: Request) -> StreamingResponse:
    engine = request.app.state.engine
    initial = _read_job(engine, job_id, owner)

    async def events() -> AsyncIterator[str]:
        state = initial
        previous = None
        idle = 0
        reconnect_at = monotonic() + 30
        while monotonic() < reconnect_at and not await request.is_disconnected():
            if state != previous:
                event = "job.failed" if state["status"] == JobStatus.FAILED else "job.status"
                yield f"event: {event}\ndata: {json.dumps(state)}\n\n"
                if state["status"] in (JobStatus.DONE, JobStatus.FAILED):
                    return
                previous = state
                idle = 0
            elif idle >= 30:
                yield ": keepalive\n\n"
                idle = 0
            await sleep(jobs.POLL_SECONDS)
            idle += 1
            try:
                state = await run_in_threadpool(_read_job, engine, job_id, owner)
            except NotFound:
                state = {**state, "status": JobStatus.FAILED, "error_code": "event_not_found"}

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
