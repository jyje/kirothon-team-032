import json
from email.message import Message
from io import BytesIO
from urllib.error import HTTPError, URLError

import pytest

from open_attendee import status


class Response(BytesIO):
    status = 200


def test_status_reports_ready_app(monkeypatch, capsys):
    data = {
        "ready": True,
        "llm": {"configured": False},
        "storage": {"backend": "local", "free_bytes": 4096},
        "internal": "extra",
    }

    def open_status(url, *, timeout):
        assert url == "http://127.0.0.1:8080/healthz"
        assert timeout == 3
        return Response(json.dumps(data).encode())

    monkeypatch.setattr(status, "urlopen", open_status)
    assert status.main([]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result == {key: data[key] for key in ("ready", "llm", "storage")}


def test_status_reports_not_ready_response(monkeypatch, capsys):
    def open_status(url, *, timeout):
        assert url == "https://example.test/app/healthz"
        raise HTTPError(url, 503, "Unavailable", Message(), BytesIO(b'{"ready": false}'))

    monkeypatch.setattr(status, "urlopen", open_status)
    assert status.main(["https://example.test/app/"]) == 1
    assert json.loads(capsys.readouterr().out) == {"ready": False}


def test_status_handles_connection_failure_without_echoing_error(monkeypatch, capsys):
    def open_status(url, *, timeout):
        raise URLError("internal detail")

    monkeypatch.setattr(status, "urlopen", open_status)
    assert status.main(["http://unreachable.test"]) == 1
    output = capsys.readouterr()
    assert not output.out
    assert "연결하지 못했어요" in output.err
    assert "internal detail" not in output.err


@pytest.mark.parametrize("body", [b"<html></html>", b'{"ready": "true"}'])
def test_status_rejects_unexpected_response(monkeypatch, capsys, body):
    monkeypatch.setattr(status, "urlopen", lambda url, *, timeout: Response(body))
    assert status.main([]) == 1
    assert not capsys.readouterr().out
