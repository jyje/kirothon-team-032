"""소유자 1명 인증, 세션 쿠키, 로그인 횟수 제한, CSRF 검사(요구사항 25.1~25.5).

- 비밀번호는 `OWNER_PASSWORD_HASH`의 argon2 해시로 확인한다.
- 세션 쿠키는 `SESSION_SECRET`으로 서명하고 `HttpOnly`, `Secure`, `SameSite=Lax`를 붙인다.
- CSRF 토큰은 "세션 씨앗"에 서명 키로 HMAC을 건 값이다. 로그인한 뒤에는 세션 쿠키 안의 씨앗을,
  로그인 전(로그인 화면)에는 익명 쿠키의 씨앗을 쓴다.
- 시크릿 값은 로그와 오류 메시지에 넣지 않는다.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import time
from collections import deque
from collections.abc import Callable
from urllib.parse import parse_qs

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Request
from fastapi.responses import PlainTextResponse, RedirectResponse, Response
from itsdangerous import BadSignature, URLSafeTimedSerializer
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from open_attendee.config import Settings

logger = logging.getLogger("open_attendee.auth")

# 소유자는 1명이다(가정 A1). 모든 데이터는 이 ID로 묶인다.
OWNER_ID = "owner"

SESSION_COOKIE = "oa_session"
CSRF_COOKIE = "oa_csrf"  # 로그인 전 화면용 익명 CSRF 씨앗
SESSION_MAX_AGE = 7 * 24 * 3600
CSRF_HEADER = "X-CSRF-Token"
CSRF_FIELD = "csrf_token"

LOGIN_PATH = "/login"
LOGIN_REDIRECT = "/sessions"
LOGIN_LIMIT = 5  # 1분 안에 허용하는 로그인 시도 수
LOGIN_WINDOW_SECONDS = 60.0

# SPA가 로그인 전에 부르는 API. 로그인 화면(SPA의 `/login`)과 빌드된 파일(`/assets/`)도 연다.
PUBLIC_PATHS = frozenset({LOGIN_PATH, "/healthz", "/api/csrf", "/api/login"})

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
# 폼 토큰을 읽으려고 본문을 메모리에 올리는 한도. 이보다 크면 헤더 토큰만 인정한다.
MAX_FORM_BODY_BYTES = 64 * 1024


def is_public_path(path: str) -> bool:
    """로그인 없이 열어 두는 경로. 로그인 화면이 쓰는 정적 파일은 시크릿이 아니라서 함께 연다."""
    return path in PUBLIC_PATHS or path.startswith(("/static/", "/assets/"))


class LoginRateLimiter:
    """IP마다 1분 창에서 `limit`회까지만 시도를 받는다. 넘으면 창이 지날 때까지 거부한다."""

    def __init__(
        self,
        limit: int = LOGIN_LIMIT,
        window: float = LOGIN_WINDOW_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.limit = limit
        self.window = window
        self._clock = clock
        self._attempts: dict[str, deque[float]] = {}

    def allow(self, ip: str) -> bool:
        """시도를 하나 기록하고 허용하면 참. 거부된 시도는 기록하지 않아 창이 늘어나지 않는다."""
        now = self._clock()
        self._prune(now)
        attempts = self._attempts.setdefault(ip, deque())
        if len(attempts) >= self.limit:
            return False
        attempts.append(now)
        return True

    def retry_after(self, ip: str) -> int:
        """거부된 IP가 다시 시도할 수 있기까지 남은 초(올림)."""
        attempts = self._attempts.get(ip)
        if not attempts:
            return 0
        remaining = self.window - (self._clock() - attempts[0])
        return max(1, int(remaining) + 1) if remaining > 0 else 0

    def _prune(self, now: float) -> None:
        for ip in list(self._attempts):
            attempts = self._attempts[ip]
            while attempts and now - attempts[0] >= self.window:
                attempts.popleft()
            if not attempts:
                del self._attempts[ip]


class Auth:
    """비밀번호 확인, 세션 쿠키 발급과 읽기, CSRF 토큰 계산."""

    def __init__(self, settings: Settings) -> None:
        self._hash = settings.owner_password_hash.reveal()
        self._key = settings.session_secret.reveal().encode()
        self._serializer = URLSafeTimedSerializer(self._key, salt="open-attendee.session")
        self._hasher = PasswordHasher()

    def verify_password(self, password: str) -> bool:
        try:
            return self._hasher.verify(self._hash, password)
        except VerificationError:
            return False
        except InvalidHashError:
            # 설정된 해시가 argon2 형식이 아니다. 값이 새지 않게 트레이스백 없이 종류만 기록한다.
            logger.error("OWNER_PASSWORD_HASH 형식이 올바르지 않습니다")  # noqa: TRY400
            return False

    def issue_session(self) -> tuple[str, str]:
        """(쿠키 값, CSRF 씨앗)을 돌려준다."""
        seed = secrets.token_urlsafe(24)
        return self._serializer.dumps({"o": OWNER_ID, "s": seed}), seed

    def read_session(self, cookie: str | None) -> str | None:
        """서명과 만료가 유효하면 CSRF 씨앗을, 아니면 `None`을 돌려준다."""
        if not cookie:
            return None
        try:
            data = self._serializer.loads(cookie, max_age=SESSION_MAX_AGE)
        except BadSignature:
            return None
        if not isinstance(data, dict) or data.get("o") != OWNER_ID:
            return None
        seed = data.get("s")
        return seed if isinstance(seed, str) and seed else None

    def csrf_token(self, seed: str) -> str:
        return hmac.new(self._key, b"csrf|" + seed.encode(), hashlib.sha256).hexdigest()

    def check_csrf(self, seed: str | None, token: str | None) -> bool:
        if not seed or not token:
            return False
        return hmac.compare_digest(self.csrf_token(seed), token)

    def new_anonymous_seed(self) -> str:
        return secrets.token_urlsafe(24)

    def set_session_cookie(self, response: Response, value: str) -> None:
        response.set_cookie(
            SESSION_COOKIE,
            value,
            max_age=SESSION_MAX_AGE,
            httponly=True,
            secure=True,
            samesite="lax",
            path="/",
        )

    def set_anonymous_csrf_cookie(self, response: Response, seed: str) -> None:
        response.set_cookie(CSRF_COOKIE, seed, httponly=True, secure=True, samesite="lax", path="/")

    def clear_cookies(self, response: Response) -> None:
        response.delete_cookie(SESSION_COOKIE, path="/", secure=True, httponly=True, samesite="lax")
        response.delete_cookie(CSRF_COOKIE, path="/", secure=True, httponly=True, samesite="lax")


def csrf_token_for(request: Request) -> str:
    """현재 요청에 맞는 CSRF 토큰. 템플릿의 폼과 `<meta>`에 넣는다."""
    auth: Auth = request.app.state.auth
    seed = getattr(request.state, "csrf_seed", None)
    return auth.csrf_token(seed) if seed else ""


def current_owner(request: Request) -> str:
    """로그인한 소유자 ID. 미들웨어가 통과시킨 요청에서만 부른다."""
    return request.state.owner_id


class AuthMiddleware(BaseHTTPMiddleware):
    """로그인과 CSRF를 한곳에서 검사한다(요구사항 25.4, 25.5)."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        auth: Auth = request.app.state.auth
        path = request.url.path

        session_seed = auth.read_session(request.cookies.get(SESSION_COOKIE))
        request.state.owner_id = OWNER_ID if session_seed else None
        request.state.csrf_seed = session_seed or request.cookies.get(CSRF_COOKIE)

        if not session_seed and not is_public_path(path):
            return self._reject_unauthenticated(request)

        # `/healthz`는 읽기 전용이라 CSRF 대상이 아니다. 나머지는 상태를 바꾸는 메서드를 검사한다.
        if request.method not in SAFE_METHODS and not await self._csrf_ok(request, auth):
            return PlainTextResponse("CSRF 토큰이 없거나 올바르지 않아요.", status_code=403)

        return await call_next(request)

    @staticmethod
    def _reject_unauthenticated(request: Request) -> Response:
        is_htmx = request.headers.get("HX-Request") == "true"
        wants_html = "text/html" in request.headers.get("accept", "")
        if request.method in SAFE_METHODS and wants_html and not is_htmx:
            return RedirectResponse(LOGIN_PATH, status_code=303)
        response = PlainTextResponse("로그인이 필요해요.", status_code=401)
        if is_htmx:
            response.headers["HX-Redirect"] = LOGIN_PATH
        return response

    @staticmethod
    async def _csrf_ok(request: Request, auth: Auth) -> bool:
        seed = request.state.csrf_seed
        token = request.headers.get(CSRF_HEADER)
        if token is None and _is_small_urlencoded_form(request):
            body = await request.body()
            fields = parse_qs(body.decode("utf-8", errors="replace"), keep_blank_values=True)
            values = fields.get(CSRF_FIELD)
            token = values[0] if values else None
        return auth.check_csrf(seed, token)


def _is_small_urlencoded_form(request: Request) -> bool:
    content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type != "application/x-www-form-urlencoded":
        return False
    try:
        # 길이를 알 수 없는(chunked) 본문은 한도를 지킬 수 없으니 헤더 토큰만 인정한다.
        length = int(request.headers["content-length"])
    except (KeyError, ValueError):
        return False
    return 0 <= length <= MAX_FORM_BODY_BYTES
