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

from open_attendee import drafts, transcript_jobs
from open_attendee.errors import ConsentRequired, NotFound, ValidationFailed
from open_attendee.llm import LLMError, LLMGateway
from open_attendee.models import (
    AssetStatus,
    EventSession,
    Job,
    JobKind,
    JobStatus,
    Template,
    utcnow,
)
from open_attendee.pipeline import summary
from open_attendee.transcription import TranscriberUnavailable

logger = logging.getLogger(__name__)
AI_KINDS = (JobKind.SUMMARY, JobKind.DRAFT)
JOB_KINDS = (*AI_KINDS, JobKind.TRANSCRIBE)
ACTIVE_STATUSES = (JobStatus.QUEUED, JobStatus.RUNNING)
MAX_ATTEMPTS = 3
LEASE = timedelta(minutes=15)
POLL_SECONDS = 0.5
HEARTBEAT_SECONDS = 60
GatewayFactory = Callable[[], LLMGateway | None]


class JobConflict(Exception):
    """다른 템플릿의 작업이 이미 진행 중이다."""


def _require_owner(db: Session, session_id: str, owner_id: str) -> EventSession:
    query = select(EventSession).where(
        EventSession.id == session_id, EventSession.owner_id == owner_id
    )
    event = db.exec(query).first()
    if event is None:
        raise NotFound
    return event


def latest_job(
    db: Session, session_id: str, owner_id: str, kind: JobKind, asset_id: str | None = None
) -> Job | None:
    _require_owner(db, session_id, owner_id)
    query = select(Job).where(
        Job.session_id == session_id, Job.owner_id == owner_id, Job.kind == kind
    )
    if asset_id is not None:
        query = query.where(col(Job.payload)["asset_id"].as_string() == asset_id)
    return db.exec(query.order_by(col(Job.created_at).desc(), col(Job.id).desc())).first()


def get_job(db: Session, job_id: str, owner_id: str) -> Job:
    job = db.get(Job, job_id)
    if job is None or job.owner_id != owner_id or job.kind not in JOB_KINDS:
        raise NotFound
    _require_owner(db, job.session_id, owner_id)
    return job


def enqueue(
    db: Session, session_id: str, owner_id: str, kind: JobKind, payload: dict[str, str]
) -> tuple[Job, bool]:
    db.connection().exec_driver_sql("BEGIN IMMEDIATE")
    _require_owner(db, session_id, owner_id)
    if kind is JobKind.TRANSCRIBE:
        asset = transcript_jobs.get_audio(db, session_id, payload["asset_id"])
        previous = latest_job(db, session_id, owner_id, kind, asset.id)
        if previous and previous.status is JobStatus.DONE:
            result = previous.model_copy()
            db.commit()
            return result, False
        transcript_jobs.audio_key(asset)
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


def claim_next(engine: Engine, kinds: tuple[JobKind, ...] = AI_KINDS) -> Job | None:
    now = utcnow()
    due = and_(col(Job.status) == JobStatus.QUEUED, col(Job.run_after) <= now)
    stale = and_(
        col(Job.status) == JobStatus.RUNNING,
        or_(col(Job.claimed_at).is_(None), col(Job.claimed_at) <= now - LEASE),
    )
    match = col(Job.kind).in_(kinds)
    with Session(engine, expire_on_commit=False) as db:
        if db.exec(select(Job.id).where(match, or_(due, stale)).limit(1)).first() is None:
            return None
        db.rollback()
        db.connection().exec_driver_sql("BEGIN IMMEDIATE")
        for job in db.exec(select(Job).where(match, stale)):
            exhausted = job.kind is not JobKind.DELETE_AUDIO and job.attempts >= MAX_ATTEMPTS
            job.status = JobStatus.FAILED if exhausted else JobStatus.QUEUED
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
    retry = retry and (job.kind is JobKind.DELETE_AUDIO or job.attempts < MAX_ATTEMPTS)
    with Session(engine) as db:
        _update_claim(
            db,
            job,
            status=JobStatus.QUEUED if retry else JobStatus.FAILED,
            claimed_at=None,
            claimed_by=None,
            last_error=code,
            run_after=utcnow() + timedelta(seconds=2 ** min(job.attempts, 8) if retry else 0),
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


def _process_transcription(
    engine: Engine, job: Job, runner: transcript_jobs.TranscriptionRunner
) -> None:
    asset_id = job.payload["asset_id"]
    with Session(engine) as db:
        _require_owner(db, job.session_id, job.owner_id)
        key = transcript_jobs.audio_key(transcript_jobs.get_audio(db, job.session_id, asset_id))
    segments = runner.run(key)

    with Session(engine) as db:
        # 철회/삭제와 결과 저장을 같은 SQLite 쓰기 잠금으로 순서화한다.
        db.connection().exec_driver_sql("BEGIN IMMEDIATE")
        event = _require_owner(db, job.session_id, job.owner_id)
        asset = transcript_jobs.get_audio(db, job.session_id, asset_id)
        if _update_claim(
            db,
            job,
            status=JobStatus.DONE,
            claimed_at=None,
            claimed_by=None,
            last_error=None,
            payload={**job.payload, "result_id": asset_id},
        ):
            if transcript_jobs.save_segments(db, asset, segments, retain_audio=event.retain_audio):
                db.add(
                    Job(
                        session_id=job.session_id,
                        owner_id=job.owner_id,
                        kind=JobKind.DELETE_AUDIO,
                        payload={"asset_id": asset_id},
                    )
                )
            db.commit()


def _remove_original(engine: Engine, job: Job, runner: transcript_jobs.TranscriptionRunner) -> None:
    asset_id = job.payload["asset_id"]
    with Session(engine) as db:
        _require_owner(db, job.session_id, job.owner_id)
        asset = transcript_jobs.get_audio(db, job.session_id, asset_id, check_consent=False)
        key = asset.blob_key if asset.status is AssetStatus.ORIGINAL_DELETE_PENDING else None
    if key:
        runner.blobs.delete(key)
    with Session(engine) as db:
        db.connection().exec_driver_sql("BEGIN IMMEDIATE")
        asset = transcript_jobs.get_audio(db, job.session_id, asset_id, check_consent=False)
        if _update_claim(
            db, job, status=JobStatus.DONE, claimed_by=None, claimed_at=None, last_error=None
        ):
            if asset.status is AssetStatus.ORIGINAL_DELETE_PENDING and asset.blob_key == key:
                asset.blob_key = None
                asset.status = AssetStatus.ORIGINAL_DELETED
                db.add(asset)
            db.commit()


def process_job(
    engine: Engine,
    job: Job,
    gateway_factory: GatewayFactory,
    transcription: transcript_jobs.TranscriptionRunner | None = None,
) -> None:
    stop = Event()
    heartbeat = Thread(target=_heartbeat, args=(engine, job, stop), daemon=True)
    heartbeat.start()
    try:
        if job.kind is JobKind.DELETE_AUDIO and transcription is not None:
            _remove_original(engine, job, transcription)
            return
        if job.kind is JobKind.TRANSCRIBE:
            if transcription is None:
                _finish_failed(engine, job, "transcriber_not_configured", retry=False)
                return
            _process_transcription(engine, job, transcription)
            return
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
    except ConsentRequired:
        _finish_failed(engine, job, "consent_required", retry=False)
    except (ValidationFailed, FileNotFoundError):
        _finish_failed(engine, job, "audio_missing", retry=False)
    except TranscriberUnavailable:
        _finish_failed(engine, job, "transcriber_not_configured", retry=False)
    except LLMError:
        _finish_failed(engine, job, "llm_failed", retry=True)
    except Exception as exc:  # noqa: BLE001 - 워커가 다음 작업을 계속 처리해야 한다.
        logger.warning("작업 처리 실패: %s", type(exc).__name__)
        _finish_failed(engine, job, "processing_failed", retry=True)
    finally:
        stop.set()
        heartbeat.join()


def worker_loop(
    engine: Engine,
    gateway_factory: GatewayFactory,
    stop: Event,
    transcription: transcript_jobs.TranscriptionRunner | None = None,
) -> None:
    if transcription is None:
        kinds = AI_KINDS
    elif transcription.transcriber is None:
        kinds = (JobKind.DELETE_AUDIO,)
    else:
        kinds = (JobKind.TRANSCRIBE, JobKind.DELETE_AUDIO)
    while not stop.is_set():
        try:
            job = claim_next(engine, kinds)
            if job is not None:
                process_job(engine, job, gateway_factory, transcription)
                continue
        except SQLAlchemyError as exc:
            logger.warning("작업 워커 실패: %s", type(exc).__name__)
        stop.wait(POLL_SECONDS)
