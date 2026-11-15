"""큐의 소유자 격리, 선점, 복구와 결과 저장 경계."""

import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlmodel import Session, select

from open_attendee import templates
from open_attendee.jobs import LEASE, claim_next, enqueue, get_job, process_job
from open_attendee.llm import LLMGateway
from open_attendee.models import (
    Draft,
    EventSession,
    Job,
    JobKind,
    JobStatus,
    LiveSummary,
    MemoBlock,
    utcnow,
)


def _event(engine: Engine) -> str:
    with Session(engine, expire_on_commit=False) as db:
        event = EventSession(owner_id="owner", title="큐 검증")
        db.add(event)
        db.add(MemoBlock(id=str(uuid4()), session_id=event.id, text="배포를 확인했다."))
        db.commit()
        return event.id


def _gateway() -> LLMGateway:
    return LLMGateway(lambda _prompt: '{"bullets":[{"text":"배포를 확인했다.","sources":["S1"]}]}')


def test_concurrent_enqueues_and_claims_share_one_job(engine: Engine) -> None:
    event = _event(engine)

    def submit() -> tuple[str, bool]:
        with Session(engine) as db:
            job, created = enqueue(db, event, "owner", JobKind.SUMMARY, {})
            return job.id, created

    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(lambda _: submit(), range(8)))
        assert len({job_id for job_id, _ in responses}) == 1
        assert sum(created for _, created in responses) == 1
        claims = list(pool.map(lambda _: claim_next(engine), range(8)))
    claimed = [job for job in claims if job]
    assert len(claimed) == 1
    assert claimed[0].attempts == 1


def test_recovered_lease_only_commits_new_workers_result(engine: Engine) -> None:
    event = _event(engine)
    with Session(engine) as db:
        job, _ = enqueue(db, event, "owner", JobKind.SUMMARY, {})
    abandoned = claim_next(engine)
    assert abandoned is not None
    with Session(engine) as db:
        row = get_job(db, job.id, "owner")
        row.claimed_at = utcnow() - LEASE - timedelta(seconds=1)
        db.commit()
    recovered = claim_next(engine)
    assert recovered is not None
    assert recovered.id == abandoned.id
    assert recovered.claimed_by != abandoned.claimed_by
    assert recovered.attempts == 2
    process_job(engine, abandoned, _gateway)
    process_job(engine, recovered, _gateway)
    with Session(engine) as db:
        final = get_job(db, job.id, "owner")
        results = db.exec(select(LiveSummary).where(LiveSummary.session_id == event)).all()
        assert final.status is JobStatus.DONE
        assert [result.id for result in results] == [final.payload["result_id"]]


def test_retry_backoff_and_attempt_limit(engine: Engine) -> None:
    event = _event(engine)
    with Session(engine) as db:
        job, _ = enqueue(db, event, "owner", JobKind.SUMMARY, {})

    def fail(_: str) -> str:
        raise RuntimeError("synthetic provider secret")

    for attempt in range(1, 4):
        claim = claim_next(engine)
        assert claim is not None
        before = utcnow()
        process_job(engine, claim, lambda: LLMGateway(fail))
        with Session(engine) as db:
            row = get_job(db, job.id, "owner")
            assert row.attempts == attempt
            assert row.last_error == "llm_failed"
            if attempt < 3:
                assert row.status is JobStatus.QUEUED
                assert row.run_after >= before + timedelta(seconds=2**attempt)
                assert claim_next(engine) is None
                row.run_after = utcnow() - timedelta(seconds=1)
                db.commit()
            else:
                assert row.status is JobStatus.FAILED


def test_new_process_recovers_persisted_claim(engine: Engine) -> None:
    event = _event(engine)
    with Session(engine) as db:
        job, _ = enqueue(db, event, "owner", JobKind.SUMMARY, {})

    old_worker = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys\n"
                "from open_attendee.db import make_engine\n"
                "from open_attendee.jobs import claim_next\n"
                "print(claim_next(make_engine(sys.argv[1])).id)"
            ),
            str(engine.url.database),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert old_worker.stdout.strip() == job.id
    engine.dispose()
    with patch("open_attendee.jobs.utcnow", return_value=utcnow() + LEASE + timedelta(seconds=1)):
        replacement = claim_next(engine)
    assert replacement is not None
    assert replacement.id == job.id
    assert replacement.attempts == 2
    process_job(engine, replacement, _gateway)
    with Session(engine) as db:
        assert get_job(db, job.id, "owner").status is JobStatus.DONE


def test_draft_uses_custom_template_snapshot_from_enqueue_time(engine: Engine) -> None:
    event = _event(engine)
    with Session(engine) as db:
        template = templates.clone_template(db, "owner", templates.BLOG_TEMPLATE_ID)
        old_name = template.name
        job, _ = enqueue(
            db, event, "owner", JobKind.DRAFT, {"template": template.model_dump_json()}
        )
        template.name = "등록 이후 이름"
        db.commit()
    claim = claim_next(engine)
    assert claim is not None
    process_job(engine, claim, lambda: LLMGateway(lambda _: '{"sections": []}'))
    with Session(engine) as db:
        final = get_job(db, job.id, "owner")
        assert final.status is JobStatus.DONE
        draft = db.get(Draft, final.payload["result_id"])
        assert draft is not None
        snapshot = templates.read_snapshot(draft)
        assert snapshot.name == old_name
        assert snapshot.sections[0].title == "들어가며"


def test_job_api_streams_safe_failure_and_hides_other_owners(
    auth_client: TestClient, db: Session
) -> None:
    assert isinstance(auth_client.app, FastAPI)
    auth_client.app.state.llm_gateway = _gateway()
    foreign = EventSession(owner_id="different-owner", title="외부 행사")
    db.add(foreign)
    foreign_job = Job(session_id=foreign.id, owner_id=foreign.owner_id, kind=JobKind.SUMMARY)
    db.add(foreign_job)
    db.commit()
    assert (
        auth_client.post(f"/api/sessions/{foreign.id}/jobs", json={"kind": "summary"}).status_code
        == 404
    )
    assert auth_client.get(f"/api/jobs/{foreign_job.id}").status_code == 404
    assert auth_client.get(f"/api/jobs/{foreign_job.id}/events").status_code == 404

    event = auth_client.post("/api/sessions", json={"title": "출처 없음"}).json()["id"]
    response = auth_client.post(f"/api/sessions/{event}/jobs", json={"kind": "summary"})
    assert response.status_code == 202
    job_id = response.json()["id"]
    stream = auth_client.get(f"/api/jobs/{job_id}/events")
    assert stream.status_code == 200
    assert "event: job.failed" in stream.text
    assert '"error_code": "no_sources"' in stream.text
    assert "payload" not in stream.text
