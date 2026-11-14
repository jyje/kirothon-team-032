"""로그에 시크릿, 프롬프트 원문, 전사 원문이 나가지 않게 하는 필터(요구사항 26.3).

두 겹으로 막는다.
1. 등록된 시크릿 값과 흔한 토큰 모양(`Bearer ...`, `sk-...`, argon2 해시)을 가린다.
2. 프롬프트와 전사 원문을 로그에 남겨야 하면 `Sensitive`로 감싼다. `str`이나 `repr`에는 글자 수만
   나온다. 코드는 원문을 직접 로그 인자로 넘기지 않는다(8.1, 9.x의 로그 규칙).

필터는 로그 레코드가 만들어지는 시점(레코드 팩토리)에 적용하므로 핸들러 설정과 상관없다.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable

REDACTED = "****"
# 너무 짧은 값은 일반 단어와 겹쳐 로그를 망가뜨리므로 시크릿으로 치지 않는다.
MIN_SECRET_LEN = 6

_TOKEN_PATTERNS = (
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}"),
    re.compile(r"\$argon2[A-Za-z0-9$=+/,.-]+"),
)


class Sensitive:
    """프롬프트나 전사 원문을 로그 호출에 넘길 때 감싸는 값. 글자 수만 드러낸다."""

    __slots__ = ("_text",)

    def __init__(self, text: str) -> None:
        self._text = text

    def reveal(self) -> str:
        return self._text

    def __repr__(self) -> str:
        return f"<redacted {len(self._text)} chars>"

    __str__ = __repr__


class Redactor:
    def __init__(self) -> None:
        self._secrets: set[str] = set()

    def add_secrets(self, values: Iterable[str | None]) -> None:
        for value in values:
            if value and len(value) >= MIN_SECRET_LEN:
                self._secrets.add(value)

    def redact_text(self, text: str) -> str:
        # 긴 값부터 바꿔야 다른 시크릿의 일부가 먼저 지워지지 않는다.
        for secret in sorted(self._secrets, key=len, reverse=True):
            text = text.replace(secret, REDACTED)
        for pattern in _TOKEN_PATTERNS:
            text = pattern.sub(REDACTED, text)
        return text

    def redact_record(self, record: logging.LogRecord) -> logging.LogRecord:
        try:
            message = record.getMessage()
        except (TypeError, ValueError):
            message = str(record.msg)
        record.msg = self.redact_text(message)
        record.args = None
        if record.exc_info and not record.exc_text:
            record.exc_text = self.redact_text(logging.Formatter().formatException(record.exc_info))
        elif record.exc_text:
            record.exc_text = self.redact_text(record.exc_text)
        return record


_redactor = Redactor()
_installed = False


def install_log_redaction(secrets: Iterable[str | None] = ()) -> Redactor:
    """모든 로그 레코드가 만들어질 때 가리기를 적용한다. 여러 번 불러도 한 번만 설치한다."""
    global _installed
    _redactor.add_secrets(secrets)
    if not _installed:
        previous = logging.getLogRecordFactory()

        def factory(*args: object, **kwargs: object) -> logging.LogRecord:
            return _redactor.redact_record(previous(*args, **kwargs))

        logging.setLogRecordFactory(factory)
        _installed = True
    return _redactor
