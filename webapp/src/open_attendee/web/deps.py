"""라우터가 함께 쓰는 의존성.

`routes_*.py`가 아니라서 `main.py`가 라우터로 자동 등록하지 않는다.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlmodel import Session

from open_attendee.assets import AssetService
from open_attendee.auth import current_owner
from open_attendee.config import Settings
from open_attendee.sessions import SessionService
from open_attendee.storage import BlobStore


def get_db(request: Request) -> Iterator[Session]:
    """요청마다 DB 세션을 하나 열고 끝나면 닫는다. 커밋은 서비스가 작업 단위마다 한다."""
    with Session(request.app.state.engine) as db:
        yield db


def get_blobs(request: Request) -> BlobStore:
    return request.app.state.blobs


def get_owner(request: Request) -> str:
    """로그인한 소유자 ID. 인증 미들웨어가 로그인하지 않은 요청을 이미 걸러 냈다."""
    return current_owner(request)


def get_session_service(
    db: Annotated[Session, Depends(get_db)], blobs: Annotated[BlobStore, Depends(get_blobs)]
) -> SessionService:
    return SessionService(db, blobs)


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_asset_service(
    db: Annotated[Session, Depends(get_db)],
    blobs: Annotated[BlobStore, Depends(get_blobs)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AssetService:
    return AssetService(db, blobs, settings)


Owner = Annotated[str, Depends(get_owner)]
Sessions = Annotated[SessionService, Depends(get_session_service)]
Assets = Annotated[AssetService, Depends(get_asset_service)]
AppSettings = Annotated[Settings, Depends(get_settings)]
