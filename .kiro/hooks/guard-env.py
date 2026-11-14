#!/usr/bin/env python3
"""에이전트가 `.env` 같은 비밀 파일을 읽지 못하게 막는 PreToolUse 훅 스크립트.

표준 입력의 JSON 전체에서 `.env`, `.env.local` 같은 경로를 찾는다. `.env.example`은 허용한다.
막으면 종료 코드 2로 끝나고, 이유는 표준 오류로 나간다.
"""

import re
import sys

PATTERN = re.compile(r"""(?:^|[\\/"'\s])\.env(?:\.(?!example\b)[\w.-]+)?(?=["'\s,}\]]|$)""")


def main() -> int:
    payload = sys.stdin.read()
    if PATTERN.search(payload):
        sys.stderr.write(
            "비밀 파일(.env)은 에이전트가 읽지 않아요. 값이 필요하면 사용자가 환경 변수로 넘겨 주세요.\n"
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
