"""LLM 호출의 한 통로(요구사항 15).

- 실제 호출은 `ask(prompt) -> str` 함수 하나로 주입한다. 운영에서는 `provider_manager.factory.ask`,
  테스트에서는 정해진 답을 돌려주는 가짜를 쓴다.
- 응답에서 첫 JSON 객체를 꺼내 검증하고, 실패하면 이유를 붙여 한 번만 다시 묻는다.
- 로그에는 제공자 이름, 걸린 시간, 입력과 출력 글자 수만 남긴다. 원문은 남기지 않는다.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from open_attendee.config import Settings

logger = logging.getLogger("open_attendee.llm")

AskFn = Callable[[str], str]
T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """호출이 실패했거나 응답을 쓸 수 없다. 메시지에는 원문을 넣지 않는다."""


def extract_json(text: str) -> object:
    """텍스트에서 처음으로 완전하게 읽히는 JSON 객체를 꺼낸다."""
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, _end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        return value
    raise ValueError("응답에서 JSON 객체를 찾지 못했어요")


class LLMGateway:
    def __init__(self, ask: AskFn, name: str = "llm") -> None:
        self._ask = ask
        self.name = name
        self.calls = 0
        self.input_chars = 0
        self.output_chars = 0

    def _call(self, prompt: str) -> str:
        started = time.monotonic()
        self.calls += 1
        self.input_chars += len(prompt)
        try:
            answer = self._ask(prompt)
        except Exception as exc:
            # 예외 메시지에 프롬프트나 키가 섞일 수 있어 종류만 남긴다.
            logger.error("LLM 호출 실패: %s (%s)", type(exc).__name__, self.name)  # noqa: TRY400
            raise LLMError("LLM 호출에 실패했어요.") from exc
        self.output_chars += len(answer)
        logger.info(
            "LLM 호출 %s: %.1f초, 입력 %d자, 출력 %d자",
            self.name,
            time.monotonic() - started,
            len(prompt),
            len(answer),
        )
        return answer

    def complete_json(self, prompt: str, schema: type[T]) -> T:
        """`schema`로 검증한 결과를 돌려준다. 첫 응답이 틀리면 이유를 붙여 한 번 더 묻는다."""
        answer = self._call(prompt)
        try:
            return schema.model_validate(extract_json(answer))
        except (ValueError, ValidationError) as first:
            reason = type(first).__name__
        retry = (
            f"{prompt}\n\n이전 응답은 형식이 맞지 않았어요({reason}). "
            "설명 없이 요청한 JSON 객체 하나만 다시 보내 주세요."
        )
        answer = self._call(retry)
        try:
            return schema.model_validate(extract_json(answer))
        except (ValueError, ValidationError) as exc:
            raise LLMError("LLM 응답을 해석하지 못했어요.") from exc


def build_gateway(settings: Settings) -> LLMGateway | None:
    """설정된 제공자로 게이트웨이를 만든다. 설정이 없거나 Codex면 `None`(요구사항 15.2, 15.8)."""
    from provider_manager import factory

    try:
        name = factory.resolve(settings.provider)
    except ValueError:
        return None
    if name == "codex" or not factory.is_configured(name):
        return None
    return LLMGateway(lambda prompt: factory.ask(prompt, name), name=name)
