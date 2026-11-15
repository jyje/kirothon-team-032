"""브라우저 테스트 전용 앱. 임시 SQLite와 정해진 모델 응답을 사용한다."""

import json
import re
from pathlib import Path
from secrets import token_hex
from tempfile import TemporaryDirectory

from argon2 import PasswordHasher

from open_attendee.config import Secret, Settings
from open_attendee.llm import LLMGateway
from open_attendee.main import create_app

_RECORD = "행사에서 배포 절차를 확인했어요."
_data = TemporaryDirectory(prefix="open-attendee-browser-")


def _answer(prompt: str) -> str:
    if "뒷받침되면" in prompt:
        return json.dumps(
            {
                "results": [
                    {
                        "index": 0,
                        "supported": True,
                        "evidence": [{"source": "S1", "quote": _RECORD}],
                    },
                    {"index": 1, "supported": False},
                ]
            }
        )
    section = re.search(r'^- id="([^"]+)"', prompt, re.MULTILINE)
    if section is None:
        raise ValueError("예상하지 못한 브라우저 테스트용 프롬프트")
    return json.dumps(
        {
            "sections": [
                {
                    "id": section[1],
                    "sentences": [
                        {"text": _RECORD, "sources": ["S1"]},
                        {"text": "배포 비용이 40% 줄었다.", "sources": ["S1"]},
                    ],
                }
            ]
        }
    )


app = create_app(
    Settings(
        owner_password_hash=Secret(
            PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash("local-browser-fixture")
        ),
        session_secret=Secret(token_hex(32)),
        data_dir=Path(_data.name),
    ),
    provider_factory=lambda: None,
)
app.state.llm_gateway = LLMGateway(_answer, name="browser-test")
