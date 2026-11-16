"""`ConsentGate`: 녹음과 다른 사람 목소리가 섞일 수 있는 음성 메모의 동의 검사(요구사항 9, 10).

검사는 화면이 아니라 서버에서 강제한다. `AssetService`(업로드)와 `JobQueue.enqueue`(전사 작업)가
같은 `require_consent`를 부른다.
"""

from __future__ import annotations

from datetime import date
from typing import Final

from pydantic import BaseModel
from sqlmodel import Session, col, select, update

from open_attendee.errors import ConsentRequired, NotFound, ValidationFailed
from open_attendee.models import (
    Asset,
    AssetKind,
    ConsentRecord,
    EventSession,
    Job,
    JobKind,
    JobStatus,
    utcnow,
)

__all__ = ["METHOD_MAX", "ConsentForm", "ConsentGate", "ConsentRequired", "is_valid_consent"]

METHOD_MAX: Final = 500


class ConsentForm(BaseModel):
    """동의 창의 입력. 세 체크 항목은 기획 문서 5.3절 3번에 해당한다."""

    informed_all: bool
    can_document: bool
    no_outside_disclosure: bool
    obtained_on: date
    method: str


def is_valid_consent(record: ConsentRecord, session_id: str) -> bool:
    """같은 세션이고, 철회되지 않았고, 세 체크 항목이 모두 참인 기록만 유효하다(요구사항 10.3)."""
    return (
        record.session_id == session_id
        and record.revoked_at is None
        and record.informed_all
        and record.can_document
        and record.no_outside_disclosure
    )


class ConsentGate:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------ 기록과 철회
    def record_consent(self, owner_id: str, session_id: str, form: ConsentForm) -> ConsentRecord:
        """세 체크 항목이 모두 참일 때만 기록을 만든다. 하나라도 거짓이면 저장하지 않는다."""
        self._owned_session(owner_id, session_id)
        if not (form.informed_all and form.can_document and form.no_outside_disclosure):
            raise ValidationFailed("동의 항목 세 개를 모두 확인해야 해요.")
        method = form.method.strip() if isinstance(form.method, str) else ""
        if not 1 <= len(method) <= METHOD_MAX:
            raise ValidationFailed(f"동의 방법은 1~{METHOD_MAX}자로 적어 주세요.")
        record = ConsentRecord(
            session_id=session_id,
            informed_all=True,
            can_document=True,
            no_outside_disclosure=True,
            obtained_on=form.obtained_on,
            method=method,
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def list_records(self, owner_id: str, session_id: str) -> list[ConsentRecord]:
        self._owned_session(owner_id, session_id)
        return list(
            self.db.exec(
                select(ConsentRecord)
                .where(ConsentRecord.session_id == session_id)
                .order_by(col(ConsentRecord.created_at).desc(), col(ConsentRecord.id).desc())
            )
        )

    def revoke(self, owner_id: str, consent_id: str) -> ConsentRecord:
        """철회 시각을 기록한다. 이미 철회된 기록은 처음 시각을 그대로 둔다."""
        record = self.db.get(ConsentRecord, consent_id)
        if record is None:
            raise NotFound("동의 기록을 찾을 수 없어요.")
        self._owned_session(owner_id, record.session_id)
        self.db.exec(
            update(ConsentRecord)
            .where(col(ConsentRecord.id) == consent_id, col(ConsentRecord.revoked_at).is_(None))
            .values(revoked_at=utcnow())
        )
        affected_audio = select(Asset.id).where(
            Asset.session_id == record.session_id, Asset.consent_id == consent_id
        )
        self.db.exec(
            update(Job)
            .where(
                Job.owner_id == owner_id,
                Job.session_id == record.session_id,
                Job.kind == JobKind.TRANSCRIBE,
                col(Job.status).in_((JobStatus.QUEUED, JobStatus.RUNNING)),
                col(Job.payload)["asset_id"].as_string().in_(affected_audio),
            )
            .values(
                status=JobStatus.FAILED,
                last_error="consent_required",
                claimed_by=None,
                claimed_at=None,
            )
        )
        self.db.commit()
        self.db.refresh(record)
        return record

    # ------------------------------------------------------------------ 판정
    def needs_consent(self, asset: Asset) -> bool:
        return asset.kind == AssetKind.RECORDING or (
            asset.kind == AssetKind.VOICE_MEMO and not asset.solo_voice
        )

    def require_consent(self, asset: Asset) -> ConsentRecord | None:
        """동의가 필요 없으면 `None`. 필요한데 유효한 기록이 없으면 `ConsentRequired`."""
        if not self.needs_consent(asset):
            return None
        record = self.db.get(ConsentRecord, asset.consent_id) if asset.consent_id else None
        if record is None or not is_valid_consent(record, asset.session_id):
            raise ConsentRequired("유효한 녹음 동의 기록이 필요해요.")
        return record

    # ------------------------------------------------------------------ 내부
    def _owned_session(self, owner_id: str, session_id: str) -> EventSession:
        event = self.db.exec(
            select(EventSession).where(
                EventSession.id == session_id, EventSession.owner_id == owner_id
            )
        ).one_or_none()
        if event is None:
            raise NotFound("세션을 찾을 수 없어요.")
        return event
