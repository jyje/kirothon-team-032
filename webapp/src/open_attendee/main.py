"""FastAPI 앱 팩토리. `web/routes_*.py`의 `router`를 자동으로 등록한다."""

from __future__ import annotations

import importlib
import logging
import os
import pkgutil
import shutil
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

from open_attendee import web
from open_attendee.auth import Auth, AuthMiddleware, LoginRateLimiter
from open_attendee.config import Settings
from open_attendee.db import init_db, make_engine
from open_attendee.errors import ConsentRequired, NotFound, UploadRejected, ValidationFailed
from open_attendee.logging_redact import install_log_redaction
from open_attendee.storage import LocalBlobStore, StorageFull
from open_attendee.web.deps import STATIC_DIR

logger = logging.getLogger("open_attendee")

# 로그와 오류 응답에서 가릴 외부 서비스 키의 환경 변수 이름.
_PROVIDER_SECRET_ENVS = (
    "OPENAI_API_KEY",
    "AWS_BEARER_TOKEN_BEDROCK",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
)


@dataclass(frozen=True)
class ProviderInfo:
    """`/healthz`에 보여 줄 LLM 제공자 요약. 키와 마스크된 키는 담지 않는다."""

    name: str
    region: str | None = None


ProviderFactory = Callable[[], ProviderInfo | None]


def resolve_provider(settings: Settings) -> ProviderInfo | None:
    """설정된 LLM 제공자를 돌려준다. 설정되지 않았으면 `None`. Codex는 추론에 쓰지 않는다."""
    from provider_manager import factory

    try:
        name = factory.resolve(settings.provider)
    except ValueError:
        return None
    if name == "codex" or not factory.is_configured(name):
        return None
    region = (
        (os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-east-1")
        if name == "bedrock"
        else None
    )
    return ProviderInfo(name=name, region=region)


def describe_llm(provider: ProviderInfo | None) -> dict[str, Any]:
    """`/healthz`용 LLM 요약. 제공자 이름과 리전만 담고 키는 마스크된 값도 넣지 않는다."""
    if provider is None:
        return {"configured": False, "provider": None, "region": None}
    return {
        "configured": True,
        "provider": provider.name,
        "region": provider.region,
    }


def discover_routers() -> list[APIRouter]:
    """`open_attendee.web`의 `routes_*` 모듈에서 `router`를 모은다."""
    routers: list[APIRouter] = []
    for info in sorted(pkgutil.iter_modules(web.__path__), key=lambda m: m.name):
        if not info.name.startswith("routes_"):
            continue
        module = importlib.import_module(f"{web.__name__}.{info.name}")
        router = getattr(module, "router", None)
        if isinstance(router, APIRouter):
            routers.append(router)
    return routers


def create_app(
    settings: Settings | None = None,
    provider_factory: ProviderFactory | None = None,
) -> FastAPI:
    """앱을 만든다. 필수 설정이 없으면 `ConfigError`로 시작을 거부한다."""
    settings = settings or Settings.from_env()
    install_log_redaction(
        [
            settings.owner_password_hash.reveal(),
            settings.session_secret.reveal(),
            *(os.environ.get(name) for name in _PROVIDER_SECRET_ENVS),
        ]
    )
    factory: ProviderFactory = provider_factory or (lambda: resolve_provider(settings))

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if settings.blob_backend != "local":
            # S3 저장소는 1단계(20.1)에서 만든다. 몰래 로컬에 쓰지 않도록 시작을 거부한다.
            raise RuntimeError("BLOB_BACKEND=s3는 아직 지원하지 않아요")
        engine = make_engine(settings.db_path)
        init_db(engine)
        app.state.engine = engine
        app.state.blobs = LocalBlobStore(settings.data_dir / "blobs")
        try:
            yield
        finally:
            engine.dispose()

    # 인증 전에 API 구조가 드러나지 않게 문서 화면은 끈다.
    app = FastAPI(
        title="Open Attendee",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.settings = settings
    app.state.provider_factory = factory
    app.state.auth = Auth(settings)
    app.state.login_limiter = LoginRateLimiter()
    app.add_middleware(AuthMiddleware)

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    for router in discover_routers():
        app.include_router(router)

    @app.get("/healthz")
    def healthz(request: Request) -> JSONResponse:
        ready = True
        try:
            with Session(request.app.state.engine) as session:
                session.connection().execute(text("SELECT 1"))
        except (SQLAlchemyError, AttributeError):
            ready = False
        try:
            free_bytes: int | None = shutil.disk_usage(settings.data_dir).free
        except OSError:
            free_bytes = None
        body = {
            "ready": ready,
            "llm": describe_llm(factory()),
            "storage": {"backend": settings.blob_backend, "free_bytes": free_bytes},
        }
        return JSONResponse(body, status_code=200 if ready else 503)

    @app.exception_handler(NotFound)
    async def not_found(_request: Request, exc: NotFound) -> JSONResponse:
        return JSONResponse({"detail": str(exc) or "찾을 수 없어요."}, status_code=404)

    @app.exception_handler(ConsentRequired)
    async def consent_required(_request: Request, exc: ConsentRequired) -> JSONResponse:
        return JSONResponse({"detail": str(exc) or "녹음 동의가 필요해요."}, status_code=403)

    @app.exception_handler(UploadRejected)
    async def upload_rejected(_request: Request, exc: UploadRejected) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=exc.status_code)

    @app.exception_handler(StorageFull)
    async def storage_full(_request: Request, _exc: StorageFull) -> JSONResponse:
        return JSONResponse({"detail": "저장 공간이 부족해요."}, status_code=507)

    @app.exception_handler(ValidationFailed)
    async def validation_failed(_request: Request, exc: ValidationFailed) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        # 기본 응답은 `input`에 요청 값을 그대로 되돌려 주므로 위치와 이유만 남긴다.
        errors = [
            {"loc": list(e.get("loc", ())), "msg": e.get("msg", ""), "type": e.get("type", "")}
            for e in exc.errors()
        ]
        return JSONResponse({"detail": errors}, status_code=422)

    @app.exception_handler(Exception)
    async def unhandled_error(_request: Request, exc: Exception) -> JSONResponse:
        # 오류 종류만 남긴다. 메시지에는 프롬프트나 전사 원문이 들어 있을 수 있다.
        logger.error("처리하지 못한 오류: %s", type(exc).__name__)
        return JSONResponse({"detail": "서버 오류가 났어요."}, status_code=500)

    return app


_app: FastAPI | None = None


def __getattr__(name: str) -> FastAPI:
    """`uvicorn open_attendee.main:app`을 위해 처음 접근할 때 앱을 만든다.

    모듈을 불러오는 것만으로는 환경 변수를 요구하지 않아서 테스트가 `create_app`을 직접 쓸 수 있다.
    """
    global _app
    if name == "app":
        if _app is None:
            _app = create_app()
        return _app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
