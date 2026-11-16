"""SQLModel 테이블과 열거형. 1단계(MVP) 몫까지 한 번에 정의한다.

소유자 격리(요구사항 25.7): 모든 테이블은 `owner_id`를 직접 갖거나 아래 사슬로 세션을 거쳐
소유자에 묶인다. 서비스 계층은 조회와 변경을 항상 `owner_id`로 한정한다.

- 직접: `EventSession`, `Job`, `Template`(내장 템플릿은 `owner_id=None`)
- `session_id`로: `MemoBlock`, `Asset`, `ConsentRecord`, `Draft`, `LiveSummary`
- `asset_id`로: `TranscriptSegment`, `DocChunk` (자료 -> 세션)
- `draft_id`로: `Fact`, `Sentence` (초안 -> 세션)

외래 키 제약은 두지 않는다. 삭제 순서는 `SessionService`가 책임진다(3.2).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel
from sqlalchemy import JSON, Column, DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy.types import TypeDecorator
from sqlmodel import Field, SQLModel


def new_id() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(UTC)


# --------------------------------------------------------------------------- 열 형식


class UTCDateTime(TypeDecorator):
    """항상 UTC로 저장하고, 읽을 때 UTC 시각 정보를 붙인다(SQLite는 tzinfo를 버리기 때문)."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Any) -> datetime | None:
        return None if value is None else value.replace(tzinfo=UTC)


def utc_column(*, nullable: bool = False, index: bool = False) -> Column:
    return Column(UTCDateTime(), nullable=nullable, index=index)


def enum_column(
    enum_cls: type[StrEnum], *, default: StrEnum | None = None, index: bool = False
) -> Column:
    """열거형을 이름이 아닌 값("queued")으로 저장한다. 원시 SQL에서 값으로 비교할 수 있다."""
    return Column(
        SAEnum(
            enum_cls,
            values_callable=lambda cls: [member.value for member in cls],
            native_enum=False,
            validate_strings=True,
            length=32,
        ),
        nullable=False,
        index=index,
        default=default,
    )


class PydanticListJSON(TypeDecorator):
    """`list[BaseModel]`을 JSON 열에 저장하고 읽을 때 다시 모델 객체로 되돌린다."""

    impl = JSON
    cache_ok = True

    def __init__(self, model: type[BaseModel]) -> None:
        super().__init__()
        self.model = model

    def process_bind_param(self, value: list[Any] | None, dialect: Any) -> list[dict] | None:
        if value is None:
            return None
        return [
            item.model_dump(mode="json") if isinstance(item, BaseModel) else item for item in value
        ]

    def process_result_value(self, value: list[dict] | None, dialect: Any) -> list[Any] | None:
        if value is None:
            return None
        return [self.model.model_validate(item) for item in value]


# --------------------------------------------------------------------------- 열거형


class AssetKind(StrEnum):
    PHOTO = "photo"
    SLIDES = "slides"  # PDF, PPTX
    REFERENCE = "reference"  # 텍스트, 마크다운, PDF
    VOICE_MEMO = "voice_memo"  # 본인 혼자 말한 메모
    RECORDING = "recording"  # 다른 사람 목소리가 담길 수 있음


class AssetStatus(StrEnum):
    STORED = "stored"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"
    ORIGINAL_DELETE_PENDING = "original_delete_pending"
    ORIGINAL_DELETED = "original_deleted"  # 전사 후 원본 음성 삭제됨


class SourceKind(StrEnum):
    MEMO = "memo"
    TRANSCRIPT = "transcript"
    PHOTO = "photo"
    DOC = "doc"
    REFERENCE = "reference"


class SentenceOrigin(StrEnum):
    AI = "ai"
    AI_EDITED = "ai_edited"
    USER_INSIGHT = "user_insight"


class VerifyStatus(StrEnum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    KEPT_AS_OPINION = "kept_as_opinion"  # 사용자가 미검증을 알고 유지
    NOT_APPLICABLE = "n/a"  # 사용자 인사이트


class DraftStatus(StrEnum):
    GENERATING = "generating"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    FAILED = "failed"


class JobKind(StrEnum):
    SUMMARY = "summary"
    DRAFT = "draft"
    PHOTO = "photo"
    DOC = "doc"
    TRANSCRIBE = "transcribe"
    DELETE_AUDIO = "delete_audio"
    DELETE_PHOTO_VERSION = "delete_photo_version"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


# --------------------------------------------------------------------------- 값 객체(열 아님)


class SourceRef(BaseModel):
    kind: SourceKind
    target_id: str  # MemoBlock.id, TranscriptSegment.id, Asset.id, DocChunk.id
    revision: int | None = None  # 메모 블록일 때 당시 revision
    locator: str  # 사람이 읽는 위치: "메모 7번째 블록", "01:12:30", "IMG_0042.jpg"


class TemplateSection(BaseModel):
    id: str
    title: str
    instruction: str  # 작성 지시. 1~2,000자
    max_sentences: int  # 1~30
    insight_slot: bool = False  # 이 섹션 끝에 인사이트 자리를 비워 둠


# --------------------------------------------------------------------------- 테이블


class EventSession(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    owner_id: str = Field(index=True)
    title: str  # 1~200자
    event_date: date | None = None
    retain_audio: bool = False  # 기본값: 전사 후 원본 음성 삭제
    created_at: datetime = Field(default_factory=utcnow, sa_column=utc_column())
    updated_at: datetime = Field(default_factory=utcnow, sa_column=utc_column())


class MemoBlock(SQLModel, table=True):
    id: str = Field(primary_key=True)  # 클라이언트가 만든 UUID. 출처의 안정된 기준
    session_id: str = Field(index=True)
    position: int = 0  # 화면 순서. 출처와 무관
    text: str = ""  # 0~10,000자
    revision: int = 1  # 저장할 때마다 1 증가
    created_at: datetime = Field(default_factory=utcnow, sa_column=utc_column())
    updated_at: datetime = Field(default_factory=utcnow, sa_column=utc_column())


class Asset(SQLModel, table=True):
    """위치 정보 열은 두지 않는다(요구사항 3.4). 촬영 시각만 `captured_at`에 둔다."""

    id: str = Field(default_factory=new_id, primary_key=True)
    session_id: str = Field(index=True)
    kind: AssetKind = Field(sa_column=enum_column(AssetKind))
    display_name: str  # 원래 파일 이름. 표시용
    blob_key: str | None = None  # 원본 음성이 삭제되면 None
    mime: str
    size_bytes: int = 0
    page_count: int | None = None  # 새로 추출한 문서의 전체 페이지 수
    captured_at: datetime | None = Field(default=None, sa_column=utc_column(nullable=True))
    consent_id: str | None = None
    solo_voice: bool = False  # 음성 메모가 본인 혼자 말한 것인지 사용자가 표시
    faces_blurred: bool = False
    face_check_confirmed: bool = False
    linked_block_id: str | None = None
    link_manual: bool = False  # 사용자가 연결을 직접 지정함. 자동 연결이 덮어쓰지 않음
    caption: str | None = None  # 사용자가 붙인 설명
    status: AssetStatus = Field(
        default=AssetStatus.STORED, sa_column=enum_column(AssetStatus, default=AssetStatus.STORED)
    )
    created_at: datetime = Field(default_factory=utcnow, sa_column=utc_column())


class ConsentRecord(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    session_id: str = Field(index=True)
    informed_all: bool  # 녹음 대상 모두에게 알리고 동의를 받음
    can_document: bool  # 동의 날짜와 방법을 기록할 수 있음
    no_outside_disclosure: bool  # 동의 범위 밖에서 공개하지 않음
    obtained_on: date
    method: str  # 예: "행사 시작 전 구두 공지와 손들기"
    revoked_at: datetime | None = Field(default=None, sa_column=utc_column(nullable=True))
    created_at: datetime = Field(default_factory=utcnow, sa_column=utc_column())


class TranscriptSegment(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    asset_id: str = Field(index=True)
    start_ms: int
    end_ms: int
    text: str
    speaker: str | None = None  # 2단계 화자 분리


class DocChunk(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    asset_id: str = Field(index=True)
    page: int  # PDF 쪽 또는 슬라이드 번호 (1부터)
    part: int = 0  # 긴 쪽을 나눈 조각 번호 (0부터)
    text: str


class Fact(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    draft_id: str = Field(index=True)
    text: str
    sources: list[SourceRef] = Field(
        default_factory=list,
        sa_column=Column(PydanticListJSON(SourceRef), nullable=False),
    )  # 비어 있으면 안 됨


class Sentence(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    draft_id: str = Field(index=True)
    section_id: str
    position: int = 0
    text: str
    origin: SentenceOrigin = Field(
        default=SentenceOrigin.AI, sa_column=enum_column(SentenceOrigin, default=SentenceOrigin.AI)
    )
    fact_ids: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    verify_status: VerifyStatus = Field(
        default=VerifyStatus.UNVERIFIED,
        sa_column=enum_column(VerifyStatus, default=VerifyStatus.UNVERIFIED),
    )
    verify_note: str | None = None


class Draft(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    session_id: str = Field(index=True)
    template_id: str
    template_snapshot: str  # 생성 당시 템플릿 JSON. 템플릿이 나중에 바뀌어도 초안은 그대로
    status: DraftStatus = Field(
        default=DraftStatus.GENERATING,
        sa_column=enum_column(DraftStatus, default=DraftStatus.GENERATING),
    )
    uses_recording: bool = False  # 녹음 전사를 출처로 썼는지
    consent_ids: list[str] | None = Field(default=None, sa_column=Column(JSON))
    approved_at: datetime | None = Field(default=None, sa_column=utc_column(nullable=True))
    created_at: datetime = Field(default_factory=utcnow, sa_column=utc_column())
    # 효과 측정(요구사항 28, 1단계 20.3).
    llm_calls: int = 0
    llm_input_chars: int = 0
    llm_output_chars: int = 0
    deleted_ai_sentences: int = 0  # 소유자가 지운 AI 문장 수
    review_seconds: int | None = None  # 마지막 기록부터 승인까지 걸린 시간
    verified_ratio: float | None = None  # 승인 때 AI 문장 중 verified 비율
    deleted_ai_ratio: float | None = None  # 승인 때 AI 문장 중 소유자가 지운 비율


class Template(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    owner_id: str | None = Field(default=None, index=True)  # None이면 내장 템플릿
    name: str
    output_kind: str  # "blog", "linkedin", 2단계: "assignment", "trip_report"
    tone: str = ""
    sections: list[TemplateSection] = Field(
        default_factory=list,
        sa_column=Column(PydanticListJSON(TemplateSection), nullable=False),
    )
    footer_note: str | None = None  # 예: 과제 템플릿의 "학습용 초안" 표시


class Job(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    owner_id: str = Field(index=True)
    session_id: str = Field(index=True)
    kind: JobKind = Field(sa_column=enum_column(JobKind))
    payload: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    status: JobStatus = Field(
        default=JobStatus.QUEUED,
        sa_column=enum_column(JobStatus, default=JobStatus.QUEUED, index=True),
    )
    attempts: int = 0
    run_after: datetime = Field(default_factory=utcnow, sa_column=utc_column())
    claimed_by: str | None = None
    claimed_at: datetime | None = Field(default=None, sa_column=utc_column(nullable=True))
    last_error: str | None = None  # 시크릿과 프롬프트 원문을 넣지 않음
    created_at: datetime = Field(default_factory=utcnow, sa_column=utc_column())


class LiveSummary(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    session_id: str = Field(index=True)
    bullets: list[dict] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    # [{"text": ..., "sources": [SourceRef...]}]
    consent_ids: list[str] | None = Field(default=None, sa_column=Column(JSON))
    covered_until: datetime = Field(default_factory=utcnow, sa_column=utc_column())
    created_at: datetime = Field(default_factory=utcnow, sa_column=utc_column())
