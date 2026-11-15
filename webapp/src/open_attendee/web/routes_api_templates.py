"""내장·사용자 템플릿 목록, 조회, 복제, 저장 API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from open_attendee import templates as svc
from open_attendee.models import Template
from open_attendee.web.deps import Db, Owner

router = APIRouter(prefix="/api/templates")


def _detail(template: Template) -> dict[str, Any]:
    return {
        "id": template.id,
        "name": template.name,
        "tone": template.tone,
        "sections": [section.model_dump() for section in template.sections],
        "built_in": template.owner_id is None,
    }


@router.get("")
def list_templates(owner: Owner, db: Db) -> dict[str, Any]:
    return {
        "templates": [
            {
                "id": template.id,
                "name": template.name,
                "sections": [section.title for section in template.sections],
            }
            for template in svc.list_templates(db, owner)
        ],
    }


@router.get("/{template_id}")
def get_template(template_id: str, owner: Owner, db: Db) -> dict[str, Any]:
    return _detail(svc.get_template(db, owner, template_id))


@router.post("/{template_id}:clone", status_code=201)
def clone_template(template_id: str, owner: Owner, db: Db) -> dict[str, Any]:
    return _detail(svc.clone_template(db, owner, template_id))


@router.put("/{template_id}", response_model=None)
def save_template(
    template_id: str, body: svc.TemplateEdit, owner: Owner, db: Db
) -> JSONResponse | dict[str, Any]:
    template = svc.get_template(db, owner, template_id)
    if template.owner_id is None:
        return JSONResponse(
            {
                "error": {
                    "code": "read_only_template",
                    "message": "내장 템플릿은 복제해 수정해 주세요.",
                }
            },
            status_code=409,
        )
    template.name = body.name
    template.tone = body.tone
    template.sections = list(body.sections)
    db.add(template)
    db.commit()
    db.refresh(template)
    return _detail(template)
