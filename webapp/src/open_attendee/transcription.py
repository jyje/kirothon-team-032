"""로컬 STT. 입력 오디오를 최대 5분의 PCM 배열로 읽어 메모리 사용을 제한한다."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING, BinaryIO, Protocol

if TYPE_CHECKING:
    from av.audio.frame import AudioFrame
    from av.audio.resampler import AudioResampler
    from av.container import InputContainer
    from faster_whisper import WhisperModel
    from numpy import float32
    from numpy.typing import NDArray

_SAMPLE_RATE = 16_000
_WINDOW_SAMPLES = 5 * 60 * _SAMPLE_RATE


@dataclass(frozen=True)
class SpeechSegment:
    start_ms: int
    end_ms: int
    text: str


class Transcriber(Protocol):
    def transcribe(self, audio: BinaryIO) -> Iterator[SpeechSegment]: ...


class TranscriberUnavailable(Exception):
    """설치된 전사기가 없어서 작업을 실행할 수 없다."""


def _audio_windows(audio: BinaryIO) -> Iterator[tuple[int, NDArray[float32]]]:
    """시작 샘플 번호와 16 kHz 모노 슬라이스를 순서대로 만든다."""
    import av
    import numpy as np
    from av.audio.resampler import AudioResampler

    buffer = np.empty(_WINDOW_SAMPLES, dtype=np.float32)
    size = 0
    offset = 0
    resampler = AudioResampler(format="flt", layout="mono", rate=_SAMPLE_RATE)
    with av.open(audio, mode="r") as container:
        for decoded in _resampled_frames(container, resampler):
            samples = decoded.to_ndarray().reshape(-1)
            while samples.size:
                count = min(samples.size, _WINDOW_SAMPLES - size)
                buffer[size : size + count] = samples[:count]
                size += count
                samples = samples[count:]
                if size == _WINDOW_SAMPLES:
                    yield offset, buffer
                    offset += size
                    size = 0
        if size:
            yield offset, buffer[:size]


def _resampled_frames(container: InputContainer, resampler: AudioResampler) -> Iterator[AudioFrame]:
    for frame in container.decode(audio=0):
        yield from resampler.resample(frame)
    yield from resampler.resample(None)


class FasterWhisperTranscriber:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name

    @cached_property
    def model(self) -> WhisperModel:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise TranscriberUnavailable("로컬 전사에 stt 의존성이 필요해요.") from exc
        return WhisperModel(self.model_name, device="cpu", compute_type="int8")

    def transcribe(self, audio: BinaryIO) -> Iterator[SpeechSegment]:
        model = self.model
        language: str | None = None
        for sample_offset, samples in _audio_windows(audio):
            offset_ms = sample_offset * 1000 // _SAMPLE_RATE
            segments, info = model.transcribe(samples, language=language, vad_filter=True)
            for segment in segments:
                text = segment.text.strip()
                if text:
                    language = info.language
                    yield SpeechSegment(
                        start_ms=offset_ms + round(segment.start * 1000),
                        end_ms=offset_ms + round(segment.end * 1000),
                        text=text,
                    )
