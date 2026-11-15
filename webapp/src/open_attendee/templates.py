"""내장 템플릿과 소유자가 관리하는 초안 템플릿."""

from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlmodel import Session, col, select

from open_attendee.errors import NotFound
from open_attendee.models import Draft, Template, TemplateSection

BLOG_TEMPLATE_ID = "builtin-blog"
BLOG_SECTIONS = [
    TemplateSection(
        id="intro",
        title="들어가며",
        instruction="행사와 이날 다룬 주제를 소개한다.",
        max_sentences=2,
    ),
    TemplateSection(
        id="body",
        title="핵심 내용",
        instruction="발표와 메모에서 알게 된 핵심 내용을 순서대로 정리한다.",
        max_sentences=6,
    ),
    TemplateSection(
        id="wrap",
        title="정리",
        instruction="기록에서 확인되는 결론이나 다음 일정만 짧게 정리한다.",
        max_sentences=2,
        insight_slot=True,
    ),
]
LINKEDIN_TEMPLATE_ID = "builtin-linkedin"
LINKEDIN_SECTIONS = [
    TemplateSection(
        id="hook",
        title="첫 문장",
        instruction="이날 가장 눈에 띈 내용 하나를 한 문장으로 던진다.",
        max_sentences=1,
    ),
    TemplateSection(
        id="points",
        title="배운 점",
        instruction="기록에서 확인되는 배운 점을 짧은 문장으로 하나씩 쓴다.",
        max_sentences=5,
    ),
    TemplateSection(
        id="closing",
        title="마무리",
        instruction="기록에 근거한 한두 문장으로 맺는다. 근거 없는 홍보 문구는 쓰지 않는다.",
        max_sentences=2,
        insight_slot=True,
    ),
]


BUILTIN_TEMPLATES: dict[str, Template] = {
    BLOG_TEMPLATE_ID: Template(
        id=BLOG_TEMPLATE_ID,
        name="블로그",
        output_kind="블로그 글",
        tone="차분하고 읽기 쉬운 설명체",
        sections=BLOG_SECTIONS,
    ),
    LINKEDIN_TEMPLATE_ID: Template(
        id=LINKEDIN_TEMPLATE_ID,
        name="링크드인",
        output_kind="링크드인 게시글",
        tone="짧고 간결한 문장",
        sections=LINKEDIN_SECTIONS,
    ),
}


class TemplateSectionEdit(TemplateSection):
    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,72}$")
    title: str = Field(min_length=1, max_length=120)
    instruction: str = Field(min_length=1, max_length=2000)
    max_sentences: int = Field(ge=1, le=30, strict=True)


class TemplateEdit(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=120)
    tone: str = Field(max_length=2000)
    sections: list[TemplateSectionEdit] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def unique_sections(self) -> TemplateEdit:
        if len({section.id for section in self.sections}) != len(self.sections):
            raise ValueError("섹션 ID는 서로 달라야 해요.")
        return self


class TemplateSnapshot(BaseModel):
    name: str | None = None
    sections: list[TemplateSection] = Field(default_factory=list)


def read_snapshot(draft: Draft) -> TemplateSnapshot:
    data = json.loads(draft.template_snapshot)
    if isinstance(data, list):
        builtin = BUILTIN_TEMPLATES.get(draft.template_id)
        data = {"name": builtin.name if builtin else None, "sections": data}
    return TemplateSnapshot.model_validate(data)


def list_templates(db: Session, owner_id: str) -> list[Template]:
    owned = db.exec(
        select(Template)
        .where(Template.owner_id == owner_id)
        .order_by(col(Template.name), col(Template.id))
    )
    return [*BUILTIN_TEMPLATES.values(), *owned]


def get_template(db: Session, owner_id: str, template_id: str) -> Template:
    builtin = BUILTIN_TEMPLATES.get(template_id)
    if builtin is not None:
        return builtin
    template = db.get(Template, template_id)
    if template is None or template.owner_id != owner_id:
        raise NotFound
    return template


def clone_template(db: Session, owner_id: str, template_id: str) -> Template:
    source = get_template(db, owner_id, template_id)
    clone = Template(
        owner_id=owner_id,
        name=f"{source.name[:117]} 사본",
        output_kind=source.output_kind,
        tone=source.tone,
        sections=[section.model_copy(deep=True) for section in source.sections],
        footer_note=source.footer_note,
    )
    db.add(clone)
    db.commit()
    db.refresh(clone)
    return clone
