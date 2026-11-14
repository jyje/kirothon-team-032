"""SPA용 JSON 인증 API: CSRF 토큰, 로그인 상태, 로그인, 로그아웃(요구사항 25.1~25.5)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from open_attendee.auth import Auth, LoginRateLimiter, csrf_token_for

router = APIRouter(prefix="/api")


class LoginBody(BaseModel):
    password: str = Field(min_length=1, max_length=1024)


def error_response(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def _csrf_response(request: Request, payload: dict | None = None) -> JSONResponse:
    """CSRF 토큰을 담아 돌려준다. 로그인 전이고 씨앗이 없으면 익명 씨앗 쿠키를 함께 내린다."""
    auth: Auth = request.app.state.auth
    new_seed: str | None = None
    if not getattr(request.state, "csrf_seed", None):
        new_seed = auth.new_anonymous_seed()
        request.state.csrf_seed = new_seed
    body = {"authenticated": bool(request.state.owner_id), **(payload or {})}
    body["csrf_token"] = csrf_token_for(request)
    response = JSONResponse(body)
    if new_seed:
        auth.set_anonymous_csrf_cookie(response, new_seed)
    return response


@router.get("/csrf")
def csrf(request: Request) -> JSONResponse:
    """로그인 상태와 CSRF 토큰. 화면이 처음 열릴 때 한 번 부른다."""
    return _csrf_response(request)


@router.post("/login")
def login(request: Request, body: LoginBody) -> Response:
    auth: Auth = request.app.state.auth
    limiter: LoginRateLimiter = request.app.state.login_limiter
    ip = request.client.host if request.client else "unknown"
    if not limiter.allow(ip):
        response = error_response(
            429, "too_many_attempts", "로그인 시도가 너무 많아요. 잠시 뒤에 다시 해 주세요."
        )
        response.headers["Retry-After"] = str(limiter.retry_after(ip))
        return response
    if not auth.verify_password(body.password):
        return error_response(401, "invalid_password", "비밀번호가 맞지 않아요.")
    cookie, seed = auth.issue_session()
    request.state.csrf_seed = seed
    request.state.owner_id = "owner"
    response = JSONResponse({"authenticated": True, "csrf_token": auth.csrf_token(seed)})
    auth.set_session_cookie(response, cookie)
    return response


@router.post("/logout")
def logout(request: Request) -> Response:
    auth: Auth = request.app.state.auth
    response = JSONResponse({"authenticated": False})
    auth.clear_cookies(response)
    return response
