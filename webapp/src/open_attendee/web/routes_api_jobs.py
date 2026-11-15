"""AI 작업 등록, 진행 상태 및 상태 변경 스트림."""

from __future__ import annotations

import json
from asyncio import sleep
from collections.abc import AsyncIterator
from time import monotonic
from typing import Any, Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import Engine
from sqlmodel import Session
from starlette.concurrency import run_in_threadpool

from open_attendee import jobs, templates
from open_attendee.errors import NotFound
from open_attendee.models import Job, JobKind, JobStatus
from open_attendee.web.deps import Db, Gateway, Owner, Sessions

router = APIRouter(prefix="/api")
AIKind = Literal["summary", "draft"]


class JobRequest(BaseModel):
    kind: AIKind
    template_id: str | None = None


def _body(job: Job) -> dict[str, Any]:
    return {
        "id": job.id,
        "kind": job.kind.value,
        "status": job.status.value,
        "attempts": job.attempts,
        "result_id": job.payload.get("result_id"),
        "dropped_bullets": int(job.payload.get("dropped_bullets", "0")),
        "truncated": job.payload.get("truncated") == "1",
        "error_code": job.last_error if job.status is JobStatus.FAILED else None,
    }


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


@router.post("/sessions/{session_id}/jobs")
def create_job(
    session_id: str, body: JobRequest, owner: Owner, sessions: Sessions, db: Db, gateway: Gateway
) -> JSONResponse:
    sessions.get(owner, session_id)
    if gateway is None:
        return _error(503, "llm_not_configured", "AI 제공자가 설정되지 않았어요.")
    kind = JobKind(body.kind)
    payload: dict[str, str] = {}
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
        return _error(409, "job_conflict", "이 행사의 다른 초안 작업이 진행 중이에요.")
    return JSONResponse(_body(job), status_code=202 if created else 200)


@router.get("/sessions/{session_id}/jobs")
def latest_job(session_id: str, kind: AIKind, owner: Owner, db: Db) -> dict[str, Any]:
    job = jobs.latest_job(db, session_id, owner, JobKind(kind))
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
