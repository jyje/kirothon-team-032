"""서비스 계층이 함께 쓰는 예외. 라우터가 HTTP 상태 코드로 바꾼다."""

from __future__ import annotations


class NotFound(LookupError):
    """객체가 없거나 요청한 소유자의 것이 아니다. 두 경우를 구분하지 않는다(요구사항 25.7)."""


class ValidationFailed(ValueError):
    """입력이 규칙을 어겼다. 메시지는 사용자에게 보여 줄 수 있는 이유만 담는다."""


class ConsentRequired(Exception):
    """동의가 필요한 자료인데 유효한 동의 기록이 없다. 라우터가 403으로 바꾼다(요구사항 10.4)."""
