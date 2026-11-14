"""uvicorn 접근 로그가 마스킹 필터를 거쳐도 깨지지 않는다."""

from __future__ import annotations

import logging

from uvicorn.logging import AccessFormatter

from open_attendee.logging_redact import Redactor


def test_access_log_keeps_args_and_masks_secrets() -> None:
    redactor = Redactor()
    redactor.add_secrets(["super-secret-value"])
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:1234", "GET", "/api/x?token=super-secret-value", "1.1", 200),
        None,
    )
    redactor.redact_record(record)
    line = AccessFormatter(use_colors=False).format(record)
    assert "super-secret-value" not in line
    assert "GET" in line
    assert "200" in line
