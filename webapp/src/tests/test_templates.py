"""사용자 템플릿의 접근 범위와 생성된 초안의 스냅샷 경계."""

from __future__ import annotations

import json
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session

from open_attendee.llm import LLMGateway
from open_attendee.models import Draft, Template

EDIT = {
    "name": "행사 요약 노트",
    "tone": "간결하게",
    "sections": [
        {
            "id": "takeaways",
            "title": "핵심 정리",
            "instruction": "확인한 내용을 요약한다.",
            "max_sentences": 1,
            "insight_slot": True,
        }
    ],
}


def clone_blog(client: TestClient) -> dict:
    response = client.post("/api/templates/builtin-blog:clone")
    assert response.status_code == 201
    return response.json()


def test_clone_save_and_use_custom_template_without_changing_draft(auth_client: TestClient) -> None:
    client = auth_client
    assert isinstance(client.app, FastAPI)
    builtin = client.get("/api/templates/builtin-blog").json()
    clone = clone_blog(client)
    assert clone["id"] != builtin["id"]
    assert not clone["built_in"]
    assert clone["sections"] == builtin["sections"]
    assert client.put("/api/templates/builtin-blog", json=EDIT).status_code == 409

    target = f"/api/templates/{clone['id']}"
    assert client.put(target, json=EDIT).status_code == 200
    assert client.get(target).json()["sections"] == EDIT["sections"]
    copied = client.post(f"{target}:clone").json()
    assert copied["id"] not in {builtin["id"], clone["id"]}
    assert copied["sections"] == EDIT["sections"]
    listing = client.get("/api/templates").json()["templates"]
    assert {"id": clone["id"], "name": EDIT["name"], "sections": ["핵심 정리"]} in listing

    event_id = client.post("/api/sessions", json={"title": "행사"}).json()["id"]
    client.put(f"/api/sessions/{event_id}/blocks/{uuid4()}", json={"text": "행사 기록"})

    def ask(prompt: str) -> str:
        assert "takeaways" in prompt
        assert "간결하게" in prompt
        return json.dumps({"sections": [{"id": "takeaways", "sentences": [{"text": "기록했다."}]}]})

    client.app.state.llm_gateway = LLMGateway(ask)
    draft_path = f"/api/sessions/{event_id}/draft"
    created = client.post(draft_path, json={"template_id": clone["id"]})
    assert created.status_code == 200, created.text
    draft = created.json()["draft"]
    assert draft["template_name"] == EDIT["name"]
    assert draft["sections"][0]["title"] == "핵심 정리"
    assert (
        client.put(
            target,
            json={
                **EDIT,
                "name": "새 형식",
                "sections": [{**EDIT["sections"][0], "title": "수정"}],
            },
        ).status_code
        == 200
    )
    assert client.get(draft_path).json()["draft"] == draft

    with Session(client.app.state.engine) as db:
        saved_draft = db.get(Draft, draft["id"])
        assert saved_draft is not None
        saved_draft.template_id = "builtin-blog"
        saved_draft.template_snapshot = json.dumps(EDIT["sections"])
        db.add(saved_draft)
        db.commit()
    legacy = client.get(draft_path).json()["draft"]
    assert legacy["template_name"] == builtin["name"]
    assert legacy["sections"][0]["title"] == "핵심 정리"


@pytest.mark.parametrize(
    "sections",
    [
        [],
        [{**EDIT["sections"][0], "id": f"s{i}"} for i in range(21)],
        [EDIT["sections"][0]] * 2,
        [{**EDIT["sections"][0], "instruction": " " * 4}],
        [{**EDIT["sections"][0], "instruction": "가" * 2001}],
        [{**EDIT["sections"][0], "max_sentences": 0}],
        [{**EDIT["sections"][0], "max_sentences": 31}],
    ],
)
def test_template_save_rejects_invalid_sections(auth_client: TestClient, sections: list) -> None:
    clone = clone_blog(auth_client)
    target = f"/api/templates/{clone['id']}"
    assert auth_client.put(target, json={**EDIT, "sections": sections}).status_code == 422
    assert auth_client.get(target).json() == clone


def test_foreign_template_cannot_be_read_cloned_or_saved(
    auth_client: TestClient, db: Session
) -> None:
    foreign = Template(owner_id="foreign", name="다른 사람의 템플릿", output_kind="blog")
    db.add(foreign)
    db.commit()
    path = f"/api/templates/{foreign.id}"
    assert auth_client.get(path).status_code == 404
    assert auth_client.post(f"{path}:clone").status_code == 404
    assert auth_client.put(path, json=EDIT).status_code == 404
    templates = auth_client.get("/api/templates").json()["templates"]
    assert foreign.id not in {template["id"] for template in templates}


def test_large_template_keeps_section_limits_and_checks_all_batches(
    auth_client: TestClient,
) -> None:
    client = auth_client
    assert isinstance(client.app, FastAPI)
    clone = clone_blog(client)
    sections = [{**EDIT["sections"][0], "id": f"s{i}", "max_sentences": 30} for i in range(7)]
    saved = client.put(f"/api/templates/{clone['id']}", json={**EDIT, "sections": sections})
    assert saved.status_code == 200
    event = client.post("/api/sessions", json={"title": "행사"}).json()["id"]
    client.put(f"/api/sessions/{event}/blocks/{uuid4()}", json={"text": "행사 기록"})
    batch_sizes = []

    def ask(prompt: str) -> str:
        if "뒷받침되면" in prompt:
            size = prompt.count("] 문장:")
            batch_sizes.append(size)
            return json.dumps(
                {
                    "results": [
                        {
                            "index": index,
                            "supported": True,
                            "evidence": [{"source": "S1", "quote": "행사 기록"}],
                        }
                        for index in range(size)
                    ]
                }
            )
        sentences = [{"text": "행사 기록", "sources": ["S1"]}] * 30
        return json.dumps(
            {"sections": [{"id": f"s{i}", "sentences": sentences} for i in [*range(7), 0]]}
        )

    client.app.state.llm_gateway = LLMGateway(ask)
    response = client.post(f"/api/sessions/{event}/draft", json={"template_id": clone["id"]})
    assert response.status_code == 200, response.text
    assert batch_sizes == [200, 10]
    draft = response.json()["draft"]
    assert draft["unverified_count"] == 0
    assert [len(section["sentences"]) for section in draft["sections"]] == [30] * 7
