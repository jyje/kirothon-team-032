"""ConsentGate와 동의 라우트 단위 테스트 (요구사항 9.1~9.4, 10.1~10.3)."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from open_attendee.consent import ConsentForm, ConsentGate
from open_attendee.errors import ConsentRequired, NotFound, ValidationFailed
from open_attendee.models import Asset, AssetKind, ConsentRecord
from open_attendee.sessions import SessionService

OWNER = "owner"
FORM = {
    "informed_all": "on",
    "can_document": "on",
    "no_outside_disclosure": "on",
    "obtained_on": "2026-11-14",
    "method": "행사 시작 전 구두 공지와 손들기",
}


def _form(**changes: object) -> ConsentForm:
    values: dict[str, object] = {
        "informed_all": True,
        "can_document": True,
        "no_outside_disclosure": True,
        "obtained_on": date(2026, 11, 14),
        "method": "구두 공지",
    }
    values.update(changes)
    return ConsentForm.model_validate(values)


def _asset(session_id: str, kind: AssetKind, consent_id: str | None = None, **kw: object) -> Asset:
    return Asset(
        session_id=session_id,
        kind=kind,
        display_name="a",
        mime="audio/webm",
        consent_id=consent_id,
        **kw,  # type: ignore[arg-type]
    )


def _count(db: Session) -> int:
    return len(db.exec(select(ConsentRecord)).all())


def test_record_consent_stores_date_and_method(db: Session, sessions: SessionService) -> None:
    event = sessions.create(OWNER, "행사")
    record = ConsentGate(db).record_consent(OWNER, event.id, _form(method="  구두 공지  "))
    assert record.session_id == event.id
    assert record.obtained_on == date(2026, 11, 14)
    assert record.method == "구두 공지"
    assert record.revoked_at is None


@pytest.mark.parametrize("field", ["informed_all", "can_document", "no_outside_disclosure"])
def test_any_unchecked_box_is_rejected_and_nothing_is_stored(
    db: Session, sessions: SessionService, field: str
) -> None:
    event = sessions.create(OWNER, "행사")
    with pytest.raises(ValidationFailed):
        ConsentGate(db).record_consent(OWNER, event.id, _form(**{field: False}))
    assert _count(db) == 0


@pytest.mark.parametrize("method", ["", "   ", "x" * 501])
def test_method_must_be_filled_in(db: Session, sessions: SessionService, method: str) -> None:
    event = sessions.create(OWNER, "행사")
    with pytest.raises(ValidationFailed):
        ConsentGate(db).record_consent(OWNER, event.id, _form(method=method))
    assert _count(db) == 0


def test_other_owners_session_looks_missing(db: Session, sessions: SessionService) -> None:
    event = sessions.create("someone-else", "행사")
    with pytest.raises(NotFound):
        ConsentGate(db).record_consent(OWNER, event.id, _form())
    assert _count(db) == 0


def test_revoke_records_time_once(db: Session, sessions: SessionService) -> None:
    event = sessions.create(OWNER, "행사")
    gate = ConsentGate(db)
    record = gate.record_consent(OWNER, event.id, _form())
    first = gate.revoke(OWNER, record.id).revoked_at
    assert first is not None
    assert gate.revoke(OWNER, record.id).revoked_at == first  # 다시 철회해도 처음 시각을 지킨다


def test_revoke_of_another_owners_record_is_not_found(
    db: Session, sessions: SessionService
) -> None:
    event = sessions.create("someone-else", "행사")
    record = ConsentGate(db).record_consent("someone-else", event.id, _form())
    with pytest.raises(NotFound):
        ConsentGate(db).revoke(OWNER, record.id)
    assert db.get(ConsentRecord, record.id).revoked_at is None  # type: ignore[union-attr]


def test_needs_consent_table(db: Session) -> None:
    gate = ConsentGate(db)
    assert gate.needs_consent(_asset("s", AssetKind.RECORDING))
    assert gate.needs_consent(_asset("s", AssetKind.RECORDING, solo_voice=True))
    assert gate.needs_consent(_asset("s", AssetKind.VOICE_MEMO, solo_voice=False))
    assert not gate.needs_consent(_asset("s", AssetKind.VOICE_MEMO, solo_voice=True))
    for kind in (AssetKind.PHOTO, AssetKind.SLIDES, AssetKind.REFERENCE):
        assert not gate.needs_consent(_asset("s", kind))


def test_require_consent_accepts_valid_record_and_skips_free_assets(
    db: Session, sessions: SessionService
) -> None:
    event = sessions.create(OWNER, "행사")
    gate = ConsentGate(db)
    record = gate.record_consent(OWNER, event.id, _form())
    assert gate.require_consent(_asset(event.id, AssetKind.RECORDING, record.id)) == record
    assert gate.require_consent(_asset(event.id, AssetKind.PHOTO)) is None
    assert gate.require_consent(_asset(event.id, AssetKind.VOICE_MEMO, solo_voice=True)) is None


def test_require_consent_rejects_missing_revoked_and_foreign_records(
    db: Session, sessions: SessionService
) -> None:
    mine = sessions.create(OWNER, "행사")
    other = sessions.create(OWNER, "다른 행사")
    gate = ConsentGate(db)
    revoked = gate.record_consent(OWNER, mine.id, _form())
    gate.revoke(OWNER, revoked.id)
    foreign = gate.record_consent(OWNER, other.id, _form())
    for consent_id in (None, "no-such-record", revoked.id, foreign.id):
        with pytest.raises(ConsentRequired):
            gate.require_consent(_asset(mine.id, AssetKind.RECORDING, consent_id))


# --------------------------------------------------------------------------- 라우트
def _session_id(client: TestClient) -> str:
    res = client.post("/api/sessions", json={"title": "행사"})
    assert res.status_code == 201
    return res.json()["id"]


def test_create_and_revoke_consent_over_http(auth_client: TestClient) -> None:
    sid = _session_id(auth_client)
    path = f"/api/sessions/{sid}/consents"
    assert auth_client.get(path).json() == {"items": []}
    created = auth_client.post(path, data=FORM)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["obtained_on"] == "2026-11-14"
    assert body["method"] == FORM["method"]
    assert body["revoked_at"] is None
    revoked = auth_client.post(f"/api/consents/{body['id']}/revoke")
    assert revoked.status_code == 200
    assert revoked.json()["revoked_at"] is not None
    assert auth_client.get(path).json() == {"items": [revoked.json()]}
    other_sid = _session_id(auth_client)
    assert auth_client.get(f"/api/sessions/{other_sid}/consents").json() == {"items": []}


def test_consent_list_looks_missing_to_another_owner(
    auth_client: TestClient, sessions: SessionService
) -> None:
    event = sessions.create("someone-else", "다른 행사")
    assert auth_client.get(f"/api/sessions/{event.id}/consents").status_code == 404


@pytest.mark.parametrize("missing", ["informed_all", "can_document", "no_outside_disclosure"])
def test_http_rejects_unchecked_box(auth_client: TestClient, missing: str) -> None:
    sid = _session_id(auth_client)
    res = auth_client.post(
        f"/api/sessions/{sid}/consents", data={k: v for k, v in FORM.items() if k != missing}
    )
    assert res.status_code == 422
    assert "동의 항목" in res.json()["detail"]


def test_http_rejects_bad_date_and_unknown_session(auth_client: TestClient) -> None:
    sid = _session_id(auth_client)
    assert (
        auth_client.post(
            f"/api/sessions/{sid}/consents", data={**FORM, "obtained_on": "내일"}
        ).status_code
        == 422
    )
    assert auth_client.post("/api/sessions/nope/consents", data=FORM).status_code == 404
    assert auth_client.post("/api/consents/nope/revoke").status_code == 404


def test_consent_routes_need_login_and_csrf(auth_client: TestClient) -> None:
    sid = _session_id(auth_client)
    token = auth_client.headers.pop("X-CSRF-Token")
    assert auth_client.post(f"/api/sessions/{sid}/consents", data=FORM).status_code == 403
    auth_client.headers["X-CSRF-Token"] = token
    anonymous = TestClient(auth_client.app, base_url="https://testserver")
    assert anonymous.post(f"/api/sessions/{sid}/consents", data=FORM).status_code == 401
    assert anonymous.get(f"/api/sessions/{sid}/consents").status_code == 401
