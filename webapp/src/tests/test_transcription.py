from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
from wave import open as wave_open

import pytest

from open_attendee import transcription


def test_whisper_uses_bounded_windows_and_keeps_source_time(monkeypatch):
    pytest.importorskip("av")
    monkeypatch.setattr(transcription, "_WINDOW_SAMPLES", 16_000)
    audio = BytesIO()
    with wave_open(audio, "wb") as wav:
        wav.setparams((1, 2, 8000, 20_000, "NONE", "not compressed"))
        wav.writeframes(b"\x00" * 40_000)
    audio.seek(0)
    requested = []

    def transcribe(samples, *, language, vad_filter):
        requested.append((samples.size, language, vad_filter))
        return iter([SimpleNamespace(start=0.1, end=0.25, text=" 합성 전사 ")]), SimpleNamespace(
            language="ko"
        )

    worker = transcription.FasterWhisperTranscriber("test")
    monkeypatch.setitem(worker.__dict__, "model", SimpleNamespace(transcribe=transcribe))
    assert list(worker.transcribe(audio)) == [
        transcription.SpeechSegment(100, 250, "합성 전사"),
        transcription.SpeechSegment(1100, 1250, "합성 전사"),
        transcription.SpeechSegment(2100, 2250, "합성 전사"),
    ]
    assert requested == [(16_000, None, True), (16_000, "ko", True), (8000, "ko", True)]
