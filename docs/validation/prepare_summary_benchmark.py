"""Prepare two synthetic, shareable cases for the event summary benchmark."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from pptx import Presentation

CASES = {
    "a": {
        "memos": [
            "동네 책 교환회는 일요일 14시부터 16시까지 주민센터 2층에서 진행한다.",
            "참가자는 최대 40명이다. 신청 여부와 관계없이 현장에서만 책을 받는다.",
            "마지막 질의응답에서 남은 책은 기증하되, 기증처는 아직 결정하지 않았다고 했다.",
        ],
        "slides": [
            "Book exchange\nBring up to 3 books per person. Textbooks are excluded.",
            "Accessibility\nThe elevator is beside the west entrance.",
        ],
        "whiteboard": ["CHECK-IN", "First 15 minutes", "Desk near the west entrance"],
    },
    "b": {
        "memos": [
            "동네 수리 모임은 토요일 10시부터 정오까지 생활문화센터 1층에서 진행한다.",
            "참가자는 최대 24명이다. 접수는 선착순이며 참가비는 무료다.",
            "마지막 질의응답에서 다음 모임을 열기로 했고 날짜는 추후 공지한다고 했다.",
        ],
        "slides": [
            "Repair meetup\nBring 1 item per person. Battery-powered devices are excluded.",
            "Accessibility\nThe ramp is beside the south entrance.",
        ],
        "whiteboard": ["CHECK-IN", "First 10 minutes", "Desk near the south entrance"],
    },
}


def prepare_cases(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for name, case in CASES.items():
        folder = output / name
        folder.mkdir(exist_ok=True)
        notes = "\n\n".join(f"{i}. {memo}" for i, memo in enumerate(case["memos"], start=1))
        (folder / "memos.md").write_text(notes + "\n", encoding="utf-8")

        deck = Presentation()
        for content in case["slides"]:
            title, body = content.split("\n")
            slide = deck.slides.add_slide(deck.slide_layouts[1])
            slide.shapes.title.text = title
            slide.placeholders[1].text = body
        deck.save(folder / "slides.pptx")

        board = Image.new("RGB", (860, 290), "#ffffff")
        ImageDraw.Draw(board).multiline_text(
            (35, 35),
            "\n".join(case["whiteboard"]),
            fill="#17202a",
            font=ImageFont.load_default(size=38),
            spacing=16,
        )
        board.save(folder / "whiteboard.png")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    prepare_cases(parser.parse_args().output)
