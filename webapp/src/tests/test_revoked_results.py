"""녹음 동의 철회 이후 결과의 접근과 생성 경합을 검증한다."""

from __future__ import annotations

import json
from datetime import date
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlmodel import Session, select

from open_attendee.consent import ConsentForm, ConsentGate
from open_attendee.db import init_db
from open_attendee.llm import LLMGateway
from open_attendee.models import (
    Asset,
    AssetKind,
    ConsentRecord,
    Draft,
    LiveSummary,
    TranscriptSegment,
)

TRANSCRIPT = "동의가 필요한 음성 원문"


@pytest.fixture
def event(auth_client: TestClient, db: Session) -> tuple[str, str]:
    event_id = auth_client.post("/api/sessions", json={"title": "철회 검증"}).json()["id"]
    auth_client.put(f"/api/sessions/{event_id}/blocks/{uuid4()}", json={"text": "남은 현장 메모"})
    record = ConsentGate(db).record_consent(
        "owner",
        event_id,
        ConsentForm(
            informed_all=True,
            can_document=True,
            no_outside_disclosure=True,
            obtained_on=date(2026, 11, 16),
            method="구두 동의",
        ),
    )
    audio = Asset(
        session_id=event_id,
        kind=AssetKind.RECORDING,
        display_name="회의.wav",
        mime="audio/wav",
        consent_id=record.id,
    )
    db.add(audio)
    db.add(TranscriptSegment(asset_id=audio.id, start_ms=0, end_ms=1000, text=TRANSCRIPT))
    db.commit()
    return event_id, record.id


def _answer(prompt: str) -> str:
    if "5~10개 항목" in prompt:
        return json.dumps({"bullets": [{"text": "생성 결과", "sources": ["S1"]}]})
    if "뒷받침되면" in prompt:
        return json.dumps(
            {
                "results": [
                    {
                        "index": 0,
                        "supported": True,
                        "evidence": [{"source": "S1", "quote": "남은 현장 메모"}],
                    }
                ]
            }
        )
    return json.dumps(
        {"sections": [{"id": "intro", "sentences": [{"text": "생성 결과", "sources": ["S1"]}]}]}
    )


@pytest.mark.parametrize("kind", ["summary", "draft"])
def test_revocation_blocks_even_uncited_input_and_allows_regeneration(
    auth_client: TestClient, db: Session, event: tuple[str, str], kind: str
) -> None:
    sid, consent_id = event
    app = auth_client.app
    assert isinstance(app, FastAPI)
    prompts: list[str] = []

    def answer(prompt: str) -> str:
        prompts.append(prompt)
        return _answer(prompt)

    app.state.llm_gateway = LLMGateway(answer)
    path = f"/api/sessions/{sid}/{kind}"
    response = auth_client.post(path)
    assert response.status_code == 200, response.text
    original = response.json()[kind]
    assert TRANSCRIPT in prompts[0]
    assert original["id"]
    if kind == "draft":
        base = f"/api/drafts/{original['id']}"
        assert auth_client.post(f"{base}/approve").status_code == 200
        assert auth_client.get(f"{base}/export.md").status_code == 200
        assert auth_client.get(f"{base}/export.html").status_code == 200

    assert auth_client.post(f"/api/consents/{consent_id}/revoke").status_code == 200
    expected = {kind: None, "llm_configured": True, "consent_blocked": True}
    assert auth_client.get(path).json() == expected
    assert auth_client.get(path, params={"result_id": original["id"]}).json() == expected
    if kind == "draft":
        sentence = original["sections"][0]["sentences"][0]["id"]
        assert (
            auth_client.patch(f"{base}/sentences/{sentence}", json={"text": "편집"}).status_code
            == 403
        )
        assert auth_client.post(f"{base}/approve").status_code == 403
        assert auth_client.get(f"{base}/export.md").status_code == 403
        assert auth_client.get(f"{base}/export.html").status_code == 403

    prompts.clear()
    response = auth_client.post(path)
    assert response.status_code == 200, response.text
    assert all(TRANSCRIPT not in prompt for prompt in prompts)
    assert auth_client.get(path).json()[kind]["id"] != original["id"]
    original_row = db.get(Draft if kind == "draft" else LiveSummary, original["id"])
    assert original_row is not None and original_row.consent_ids == [consent_id]


@pytest.mark.parametrize("kind", ["summary", "draft"])
def test_revocation_during_generation_discards_result(
    auth_client: TestClient, db: Session, event: tuple[str, str], kind: str
) -> None:
    sid, consent_id = event
    app = auth_client.app
    assert isinstance(app, FastAPI)

    def answer(prompt: str) -> str:
        assert TRANSCRIPT in prompt
        with Session(app.state.engine) as other:
            ConsentGate(other).revoke("owner", consent_id)
        return _answer(prompt)

    app.state.llm_gateway = LLMGateway(answer)
    response = auth_client.post(f"/api/sessions/{sid}/{kind}")
    assert response.status_code == 403, response.text
    assert db.exec(select(Draft if kind == "draft" else LiveSummary)).first() is None


def test_legacy_results_without_consent_columns_are_migrated(
    auth_client: TestClient, db: Session, engine: Engine, event: tuple[str, str]
) -> None:
    sid, consent_id = event
    legacy_summary = LiveSummary(session_id=sid)
    legacy_draft = Draft(
        session_id=sid, template_id="builtin-blog", template_snapshot="{}", uses_recording=True
    )
    unaffected_draft = Draft(session_id=sid, template_id="builtin-blog", template_snapshot="{}")
    db.add_all([legacy_summary, legacy_draft, unaffected_draft])
    db.commit()
    ids = [legacy_summary.id, legacy_draft.id, unaffected_draft.id]
    db.rollback()
    with engine.begin() as conn:
        conn.exec_driver_sql("ALTER TABLE draft DROP COLUMN consent_ids")
        conn.exec_driver_sql("ALTER TABLE livesummary DROP COLUMN consent_ids")

    init_db(engine)
    assert db.get(ConsentRecord, consent_id) is not None
    ConsentGate(db).revoke("owner", consent_id)
    for kind, result_id in zip(("summary", "draft", "draft"), ids, strict=True):
        response = auth_client.get(f"/api/sessions/{sid}/{kind}", params={"result_id": result_id})
        assert response.status_code == 200
        assert response.json().get("consent_blocked", False) is (result_id != ids[-1])
