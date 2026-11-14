"""라우터가 함께 쓰는 Jinja2 템플릿 설정과 의존성.

`routes_*.py`가 아니라서 `main.py`가 라우터로 자동 등록하지 않는다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.templating import Jinja2Templates

from open_attendee.auth import csrf_token_for

WEB_DIR = Path(__file__).parent
STATIC_DIR = WEB_DIR / "static"
TEMPLATES_DIR = WEB_DIR / "templates"


def _base_context(request: Request) -> dict[str, Any]:
    """모든 화면이 쓰는 값: CSRF 토큰(`<meta>`와 폼)과 로그인 여부."""
    return {
        "csrf_token": csrf_token_for(request),
        "logged_in": bool(getattr(request.state, "owner_id", None)),
    }


templates = Jinja2Templates(directory=TEMPLATES_DIR, context_processors=[_base_context])
