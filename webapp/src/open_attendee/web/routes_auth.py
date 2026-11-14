"""로그인과 로그아웃 라우트(요구사항 25.1~25.3)."""

from __future__ import annotations

import html
from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from open_attendee.auth import (
    LOGIN_PATH,
    LOGIN_REDIRECT,
    Auth,
    LoginRateLimiter,
    csrf_token_for,
)

router = APIRouter()


def _login_page(request: Request, *, error: str | None = None, status_code: int = 200) -> Response:
    """로그인 화면. 로그인 전에도 CSRF 토큰이 필요해서 익명 씨앗 쿠키를 함께 내려 준다."""
    auth: Auth = request.app.state.auth
    new_seed: str | None = None
    if not getattr(request.state, "csrf_seed", None):
        new_seed = auth.new_anonymous_seed()
        request.state.csrf_seed = new_seed
    token = html.escape(csrf_token_for(request))
    message = f'<p role="alert">{html.escape(error)}</p>' if error else ""
    body = (
        '<!doctype html><html lang="ko"><meta charset="utf-8"><title>로그인</title>'
        f"<main>{message}"
        f'<form method="post" action="{LOGIN_PATH}">'
        f'<input type="hidden" name="csrf_token" value="{token}">'
        '<label>비밀번호 <input type="password" name="password" autocomplete="current-password"'
        " required></label>"
        '<button type="submit">로그인</button></form></main></html>'
    )
    response = HTMLResponse(body, status_code=status_code)
    if new_seed:
        auth.set_anonymous_csrf_cookie(response, new_seed)
    return response


@router.get(LOGIN_PATH)
def login_form(request: Request) -> Response:
    if request.state.owner_id:
        return RedirectResponse(LOGIN_REDIRECT, status_code=303)
    return _login_page(request)


@router.post(LOGIN_PATH)
def login(request: Request, password: Annotated[str, Form()]) -> Response:
    auth: Auth = request.app.state.auth
    limiter: LoginRateLimiter = request.app.state.login_limiter
    ip = request.client.host if request.client else "unknown"
    if not limiter.allow(ip):
        response = _login_page(
            request, error="로그인 시도가 너무 많아요. 잠시 뒤에 다시 해 주세요.", status_code=429
        )
        response.headers["Retry-After"] = str(limiter.retry_after(ip))
        return response
    if not auth.verify_password(password):
        return _login_page(request, error="비밀번호가 맞지 않아요.", status_code=401)
    cookie, _seed = auth.issue_session()
    response = RedirectResponse(LOGIN_REDIRECT, status_code=303)
    auth.set_session_cookie(response, cookie)
    return response


@router.post("/logout")
def logout(request: Request) -> Response:
    auth: Auth = request.app.state.auth
    response = RedirectResponse(LOGIN_PATH, status_code=303)
    auth.clear_cookies(response)
    return response
