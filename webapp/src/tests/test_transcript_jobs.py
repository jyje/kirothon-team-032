from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from io import BytesIO
from typing import BinaryIO

from sqlalchemy import Engine
from sqlmodel import Session

from open_attendee import jobs
from open_attendee.assets import AssetService
from open_attendee.config import Settings
from open_attendee.consent import ConsentForm, ConsentGate
from open_attendee.models import Asset, AssetKind, AssetStatus, JobKind, JobStatus, utcnow
from open_attendee.pipeline.sources import build_source_map
from open_attendee.sessions import SessionService
from open_attendee.storage import LocalBlobStore
from open_attendee.transcript_jobs import TranscriptionRunner, list_segments
from open_attendee.transcription import SpeechSegment

OWNER = "owner"
WAV = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 32


def _audio(db, sessions, blobs, settings):
    event = sessions.create(OWNER, "전사 확인")
    consent = ConsentGate(db).record_consent(
        OWNER,
        event.id,
        ConsentForm(
            informed_all=True,
            can_document=True,
            no_outside_disclosure=True,
            obtained_on=date(2026, 11, 14),
            method="구두 동의",
        ),
    )
    audio = AssetService(db, blobs, settings).store_upload(
        OWNER,
        event.id,
        AssetKind.VOICE_MEMO,
        "voice.wav",
        BytesIO(WAV),
        consent.id,
    )
    return event.id, consent.id, audio.id


def test_transcription_commits_result_and_uses_stable_sources(
    engine: Engine, db: Session, sessions: SessionService, blobs: LocalBlobStore, settings: Settings
) -> None:
    event_id, consent_id, audio_id = _audio(db, sessions, blobs, settings)

    class Model:
        def transcribe(self, audio: BinaryIO) -> Iterator[SpeechSegment]:
            assert audio.read() == WAV
            yield SpeechSegment(100, 1500, "합성 음성")

    job, created = jobs.enqueue(db, event_id, OWNER, JobKind.TRANSCRIBE, {"asset_id": audio_id})
    assert created
    assert jobs.claim_next(engine) is None
    claimed = jobs.claim_next(engine, (JobKind.TRANSCRIBE,))
    assert claimed and claimed.id == job.id
    jobs.process_job(engine, claimed, lambda: None, TranscriptionRunner(blobs, Model()))

    with Session(engine) as check:
        done = jobs.get_job(check, job.id, OWNER)
        assert done.status == JobStatus.DONE
        assert done.payload["result_id"] == audio_id
        segments = list_segments(check, audio_id)
        assert len(segments) == 1
        assert check.get(Asset, audio_id).status == AssetStatus.READY
        source = build_source_map(check, event_id).items[0].ref
        assert source.target_id == segments[0].id
        assert source.locator == "voice.wav 00:00:00.100~00:00:01.500"
        existing, created = jobs.enqueue(
            check, event_id, OWNER, JobKind.TRANSCRIBE, {"asset_id": audio_id}
        )
        assert not created and existing.id == job.id
        ConsentGate(check).revoke(OWNER, consent_id)
        assert not build_source_map(check, event_id).items


def test_revocation_during_decode_leaves_no_result(
    engine: Engine, db: Session, sessions: SessionService, blobs: LocalBlobStore, settings: Settings
) -> None:
    event_id, consent_id, audio_id = _audio(db, sessions, blobs, settings)

    class Model:
        def transcribe(self, _audio: BinaryIO) -> Iterator[SpeechSegment]:
            with Session(engine) as revoke_db:
                ConsentGate(revoke_db).revoke(OWNER, consent_id)
            yield SpeechSegment(100, 1500, "저장되지 않아야 해요")

    job, _ = jobs.enqueue(db, event_id, OWNER, JobKind.TRANSCRIBE, {"asset_id": audio_id})
    claimed = jobs.claim_next(engine, (JobKind.TRANSCRIBE,))
    assert claimed
    jobs.process_job(engine, claimed, lambda: None, TranscriptionRunner(blobs, Model()))
    with Session(engine) as check:
        failed = jobs.get_job(check, job.id, OWNER)
        assert failed.status == JobStatus.FAILED
        assert failed.last_error == "consent_required"
        assert not list_segments(check, audio_id)


def test_transient_failure_retries_without_partial_segments(
    engine: Engine, db: Session, sessions: SessionService, blobs: LocalBlobStore, settings: Settings
) -> None:
    event_id, _, audio_id = _audio(db, sessions, blobs, settings)
    failures_remaining = 1

    class Model:
        def transcribe(self, _audio: BinaryIO) -> Iterator[SpeechSegment]:
            nonlocal failures_remaining
            yield SpeechSegment(100, 1500, "재시도")
            if failures_remaining:
                failures_remaining -= 1
                raise RuntimeError("temporary failure")

    job, _ = jobs.enqueue(db, event_id, OWNER, JobKind.TRANSCRIBE, {"asset_id": audio_id})
    runner = TranscriptionRunner(blobs, Model())
    claim = jobs.claim_next(engine, (JobKind.TRANSCRIBE,))
    assert claim
    jobs.process_job(engine, claim, lambda: None, runner)
    with Session(engine) as check:
        queued = jobs.get_job(check, job.id, OWNER)
        assert queued.status == JobStatus.QUEUED and queued.attempts == 1
        assert not list_segments(check, audio_id)
        queued.run_after = utcnow()
        check.add(queued)
        check.commit()
    retry = jobs.claim_next(engine, (JobKind.TRANSCRIBE,))
    assert retry and retry.attempts == 2
    jobs.process_job(engine, retry, lambda: None, runner)
    with Session(engine) as check:
        assert jobs.get_job(check, job.id, OWNER).status == JobStatus.DONE
        assert len(list_segments(check, audio_id)) == 1
