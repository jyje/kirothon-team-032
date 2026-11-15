"""SQLite 작업 큐. 결과와 완료 상태를 같은 트랜잭션에 저장한다."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import timedelta
from threading import Event, Thread
from uuid import uuid4

from sqlalchemy import Engine, and_, or_, update
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, col, select

from open_attendee import drafts
from open_attendee.errors import NotFound
from open_attendee.llm import LLMError, LLMGateway
from open_attendee.models import EventSession, Job, JobKind, JobStatus, Template, utcnow
from open_attendee.pipeline import summary

logger = logging.getLogger(__name__)
AI_KINDS = (JobKind.SUMMARY, JobKind.DRAFT)
ACTIVE_STATUSES = (JobStatus.QUEUED, JobStatus.RUNNING)
MAX_ATTEMPTS = 3
LEASE = timedelta(minutes=15)
POLL_SECONDS = 0.5
HEARTBEAT_SECONDS = 60
GatewayFactory = Callable[[], LLMGateway | None]


class JobConflict(Exception):
    """다른 템플릿의 작업이 이미 진행 중이다."""


def _require_owner(db: Session, session_id: str, owner_id: str) -> None:
    owned = select(EventSession.id).where(
        EventSession.id == session_id, EventSession.owner_id == owner_id
    )
    if db.exec(owned).first() is None:
        raise NotFound


def latest_job(db: Session, session_id: str, owner_id: str, kind: JobKind) -> Job | None:
    _require_owner(db, session_id, owner_id)
    return db.exec(
        select(Job)
        .where(Job.session_id == session_id, Job.owner_id == owner_id, Job.kind == kind)
        .order_by(col(Job.created_at).desc(), col(Job.id).desc())
    ).first()


def get_job(db: Session, job_id: str, owner_id: str) -> Job:
    job = db.get(Job, job_id)
    if job is None or job.owner_id != owner_id or job.kind not in AI_KINDS:
        raise NotFound
    _require_owner(db, job.session_id, owner_id)
    return job


def enqueue(
    db: Session, session_id: str, owner_id: str, kind: JobKind, payload: dict[str, str]
) -> tuple[Job, bool]:
    db.connection().exec_driver_sql("BEGIN IMMEDIATE")
    _require_owner(db, session_id, owner_id)
    active = db.exec(
        select(Job).where(
            Job.session_id == session_id,
            Job.owner_id == owner_id,
            Job.kind == kind,
            col(Job.status).in_(ACTIVE_STATUSES),
        )
    ).first()
    if active is not None:
        if active.payload != payload:
            raise JobConflict
        result = active.model_copy()
        db.commit()
        return result, False
    job = Job(session_id=session_id, owner_id=owner_id, kind=kind, payload=payload)
    db.add(job)
    db.flush()
    result = job.model_copy()
    db.commit()
    return result, True


def claim_next(engine: Engine) -> Job | None:
    now = utcnow()
    due = and_(col(Job.status) == JobStatus.QUEUED, col(Job.run_after) <= now)
    stale = and_(
        col(Job.status) == JobStatus.RUNNING,
        or_(col(Job.claimed_at).is_(None), col(Job.claimed_at) <= now - LEASE),
    )
    match = col(Job.kind).in_(AI_KINDS)
    with Session(engine, expire_on_commit=False) as db:
        if db.exec(select(Job.id).where(match, or_(due, stale)).limit(1)).first() is None:
            return None
        db.rollback()
        db.connection().exec_driver_sql("BEGIN IMMEDIATE")
        for job in db.exec(select(Job).where(match, stale)):
            job.status = JobStatus.FAILED if job.attempts >= MAX_ATTEMPTS else JobStatus.QUEUED
            job.last_error = "worker_interrupted"
            job.claimed_by = None
            job.claimed_at = None
            job.run_after = now
        db.flush()
        job = db.exec(
            select(Job).where(match, due).order_by(col(Job.created_at), col(Job.id)).limit(1)
        ).first()
        if job is not None:
            job.status = JobStatus.RUNNING
            job.attempts += 1
            job.claimed_by = uuid4().hex
            job.claimed_at = now
        db.commit()
        return job


def _update_claim(db: Session, job: Job, **values: object) -> bool:
    statement = (
        update(Job)
        .where(
            col(Job.id) == job.id,
            col(Job.status) == JobStatus.RUNNING,
            col(Job.claimed_by) == job.claimed_by,
        )
        .values(**values)
        .returning(col(Job.id))
    )
    return db.execute(statement).scalar_one_or_none() is not None


def _finish_failed(engine: Engine, job: Job, code: str, *, retry: bool) -> None:
    retry = retry and job.attempts < MAX_ATTEMPTS
    with Session(engine) as db:
        _update_claim(
            db,
            job,
            status=JobStatus.QUEUED if retry else JobStatus.FAILED,
            claimed_at=None,
            claimed_by=None,
            last_error=code,
            run_after=utcnow() + timedelta(seconds=2**job.attempts if retry else 0),
        )
        db.commit()


def _heartbeat(engine: Engine, job: Job, stop: Event) -> None:
    while not stop.wait(HEARTBEAT_SECONDS):
        try:
            with Session(engine) as db:
                if not _update_claim(db, job, claimed_at=utcnow()):
                    return
                db.commit()
        except SQLAlchemyError as exc:
            logger.warning("작업 임대 갱신 실패: %s", type(exc).__name__)


def process_job(engine: Engine, job: Job, gateway_factory: GatewayFactory) -> None:
    stop = Event()
    heartbeat = Thread(target=_heartbeat, args=(engine, job, stop), daemon=True)
    heartbeat.start()
    try:
        gateway = gateway_factory()
        if gateway is None:
            _finish_failed(engine, job, "llm_not_configured", retry=False)
            return
        with Session(engine) as db:
            _require_owner(db, job.session_id, job.owner_id)
            payload = dict(job.payload)
            if job.kind is JobKind.DRAFT:
                template = Template.model_validate(json.loads(job.payload["template"]))
                result_id = drafts.generate_draft(db, gateway, job.session_id, template).id
            else:
                result = summary.generate_summary(db, gateway, job.session_id)
                result_id = result.summary.id
                payload.update(
                    dropped_bullets=str(result.dropped_bullets),
                    truncated=str(int(result.truncated)),
                )
            if _update_claim(
                db,
                job,
                status=JobStatus.DONE,
                claimed_at=None,
                claimed_by=None,
                last_error=None,
                payload={**payload, "result_id": result_id},
            ):
                db.commit()
    except (NotFound, drafts.NoSources, summary.NoSources) as exc:
        code = "event_not_found" if isinstance(exc, NotFound) else "no_sources"
        _finish_failed(engine, job, code, retry=False)
    except LLMError:
        _finish_failed(engine, job, "llm_failed", retry=True)
    except Exception as exc:  # noqa: BLE001 - 워커가 다음 작업을 계속 처리해야 한다.
        logger.warning("작업 처리 실패: %s", type(exc).__name__)
        _finish_failed(engine, job, "processing_failed", retry=True)
    finally:
        stop.set()
        heartbeat.join()


def worker_loop(engine: Engine, gateway_factory: GatewayFactory, stop: Event) -> None:
    while not stop.is_set():
        try:
            job = claim_next(engine)
            if job is not None:
                process_job(engine, job, gateway_factory)
                continue
        except SQLAlchemyError as exc:
            logger.warning("작업 워커 실패: %s", type(exc).__name__)
        stop.wait(POLL_SECONDS)
