"""실행 중인 Open Attendee의 준비 상태를 확인하는 명령."""

from __future__ import annotations

import argparse
import json
import sys
from http import HTTPStatus
from http.client import HTTPException
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import urlopen


def health_url(base: str) -> str:
    try:
        url = urlsplit(base)
    except ValueError:
        raise argparse.ArgumentTypeError("올바른 앱 주소를 입력해 주세요.") from None
    if url.scheme not in {"http", "https"} or not url.hostname:
        raise argparse.ArgumentTypeError("앱 주소는 http:// 또는 https://로 시작해야 해요.")
    if url.username is not None or url.password is not None or url.query or url.fragment:
        raise argparse.ArgumentTypeError("앱 주소에는 사용자 정보, 쿼리, 프래그먼트를 넣지 마세요.")
    return url._replace(path=url.path.rstrip("/") + "/healthz").geturl()


def read_status(url: str) -> tuple[int, object]:
    try:
        with urlopen(url, timeout=3) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        with error:
            if error.code != HTTPStatus.SERVICE_UNAVAILABLE:
                raise
            return error.code, json.load(error)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Open Attendee의 준비 상태를 확인합니다.")
    parser.add_argument(
        "url",
        nargs="?",
        type=health_url,
        default="http://127.0.0.1:8080",
        help="실행 중인 앱 주소 (기본값 http://127.0.0.1:8080)",
    )
    args = parser.parse_args(argv)
    try:
        code, data = read_status(args.url)
    except HTTPError as error:
        print(f"상태 점검 요청이 실패했어요 (HTTP {error.code}).", file=sys.stderr)
        return 1
    except (OSError, HTTPException):
        print("상태 점검 주소에 연결하지 못했어요.", file=sys.stderr)
        return 1
    except ValueError:
        print("상태 점검 응답을 읽지 못했어요.", file=sys.stderr)
        return 1

    if not isinstance(data, dict) or not isinstance(data.get("ready"), bool):
        print("상태 점검 응답에서 준비 상태를 찾지 못했어요.", file=sys.stderr)
        return 1
    summary = {key: data[key] for key in ("ready", "llm", "storage") if key in data}
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if code == HTTPStatus.OK and data["ready"] else 1


if __name__ == "__main__":
    sys.exit(main())
