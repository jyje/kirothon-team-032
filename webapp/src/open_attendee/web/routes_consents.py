"""녹음 동의 기록과 철회 라우트(요구사항 9.1~9.4)."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Form
from fastapi.responses import JSONResponse
from sqlmodel import Session

from open_attendee.consent import ConsentForm, ConsentGate
from open_attendee.errors import ValidationFailed
from open_attendee.models import ConsentRecord
from open_attendee.web.deps import Owner, get_db

router = APIRouter()


def get_consent_gate(db: Annotated[Session, Depends(get_db)]) -> ConsentGate:
    return ConsentGate(db)


Gate = Annotated[ConsentGate, Depends(get_consent_gate)]


def _body(record: ConsentRecord) -> dict[str, object]:
    return {
        "id": record.id,
        "session_id": record.session_id,
        "obtained_on": record.obtained_on.isoformat(),
        "method": record.method,
        "revoked_at": record.revoked_at.isoformat() if record.revoked_at else None,
    }


@router.post("/sessions/{session_id}/consents")
def create_consent(
    session_id: str,
    owner: Owner,
    gate: Gate,
    obtained_on: Annotated[str, Form()] = "",
    method: Annotated[str, Form()] = "",
    informed_all: Annotated[bool, Form()] = False,
    can_document: Annotated[bool, Form()] = False,
    no_outside_disclosure: Annotated[bool, Form()] = False,
) -> JSONResponse:
    try:
        day = date.fromisoformat(obtained_on.strip())
    except ValueError as exc:
        raise ValidationFailed("동의 날짜는 YYYY-MM-DD 형식이어야 해요.") from exc
    form = ConsentForm(
        informed_all=informed_all,
        can_document=can_document,
        no_outside_disclosure=no_outside_disclosure,
        obtained_on=day,
        method=method,
    )
    record = gate.record_consent(owner, session_id, form)
    return JSONResponse(_body(record), status_code=201)


@router.post("/consents/{consent_id}/revoke")
def revoke_consent(consent_id: str, owner: Owner, gate: Gate) -> JSONResponse:
    return JSONResponse(_body(gate.revoke(owner, consent_id)))
