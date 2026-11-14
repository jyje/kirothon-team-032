"""`PhotoProcessor.sanitize` 단위 테스트(요구사항 3.3~3.8)."""

from __future__ import annotations

import io
from datetime import UTC, timedelta, timezone

import pytest
from PIL import Image

from open_attendee.processors.photo import (
    MAX_LONG_SIDE,
    THUMBNAIL_LONG_SIDE,
    InvalidImage,
    PhotoProcessor,
    parse_exif_time,
)
from tests.imaging import make_exif, make_image, make_split_image, utc

processor = PhotoProcessor()


def reopen(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data))


def test_촬영_시각만_읽고_EXIF는_모두_지운다() -> None:
    raw = make_image(exif=make_exif(captured="2026:11:14 10:30:00", offset="+09:00"))
    result = processor.sanitize(raw)

    assert result.captured_at == utc("2026-11-14T01:30:00")
    assert len(reopen(result.data).getexif()) == 0
    assert len(reopen(result.thumbnail).getexif()) == 0
    assert b"Exif" not in result.data
    assert b"Exif" not in result.thumbnail


def test_시간대가_없으면_기본값_UTC로_해석한다() -> None:
    raw = make_image(exif=make_exif(captured="2026:11:14 10:30:00"))
    assert processor.sanitize(raw).captured_at == utc("2026-11-14T10:30:00")


def test_기본_시간대를_매개변수로_바꿀_수_있다() -> None:
    raw = make_image(exif=make_exif(captured="2026:11:14 10:30:00"))
    kst = timezone(timedelta(hours=9))
    assert processor.sanitize(raw, default_tz=kst).captured_at == utc("2026-11-14T01:30:00")


def test_EXIF에_시간대_오프셋이_있으면_기본값보다_우선한다() -> None:
    raw = make_image(exif=make_exif(captured="2026:11:14 10:30:00", offset="-05:00"))
    kst = timezone(timedelta(hours=9))
    assert processor.sanitize(raw, default_tz=kst).captured_at == utc("2026-11-14T15:30:00")


@pytest.mark.parametrize("captured", [None, "", "not a time", "0000:00:00 00:00:00"])
def test_촬영_시각이_없거나_읽을_수_없으면_None(captured: str | None) -> None:
    raw = make_image(exif=make_exif(captured=captured))
    assert processor.sanitize(raw).captured_at is None


def test_EXIF가_아예_없는_사진도_처리한다() -> None:
    result = processor.sanitize(make_image())
    assert result.captured_at is None
    assert result.mime == "image/jpeg"


@pytest.mark.parametrize("value", [None, 5, b"2026:11:14 10:30:00"])
def test_시각_문자열이_아니면_None(value: object) -> None:
    assert parse_exif_time(value) is None


def test_잘못된_오프셋은_무시하고_기본_시간대를_쓴다() -> None:
    assert parse_exif_time("2026:11:14 10:30:00", "+99:99") == utc("2026-11-14T10:30:00")
    assert parse_exif_time("2026:11:14 10:30:00", "KST") == utc("2026-11-14T10:30:00")


def test_회전_정보를_픽셀에_반영한다() -> None:
    # Orientation 6: 화면에서는 시계 방향으로 90도 돌려 보이는 사진. 가로 40x20이 세로 20x40이 된다.
    raw = make_split_image((40, 20), make_exif(orientation=6))
    result = processor.sanitize(raw)

    image = reopen(result.data).convert("RGB")
    assert image.size == (20, 40)
    top, bottom = image.getpixel((10, 2)), image.getpixel((10, 37))
    assert top[0] > 200 > top[2]  # 원본의 왼쪽(빨강)이 위로 간다
    assert bottom[2] > 200 > bottom[0]
    assert len(image.getexif()) == 0


def test_HEIC는_JPEG로_바꿔_저장한다() -> None:
    raw = make_image((64, 48), fmt="HEIF", exif=make_exif())
    result = processor.sanitize(raw)

    assert result.mime == "image/jpeg"
    image = reopen(result.data)
    assert image.format == "JPEG"
    assert image.size == (64, 48)
    assert len(image.getexif()) == 0
    assert result.captured_at == utc("2026-11-14T10:30:00")


def test_PNG는_PNG로_저장한다() -> None:
    result = processor.sanitize(make_image((10, 10), fmt="PNG", exif=make_exif()))
    assert result.mime == "image/png"
    assert reopen(result.data).format == "PNG"


def test_투명한_PNG의_알파를_유지하고_축소판은_흰_배경_JPEG다() -> None:
    raw = make_image((30, 30), fmt="PNG", mode="RGBA", color=(0, 0, 0, 0))
    result = processor.sanitize(raw)

    assert reopen(result.data).mode == "RGBA"
    thumb = reopen(result.thumbnail)
    assert thumb.format == "JPEG"
    assert thumb.convert("RGB").getpixel((5, 5)) == (255, 255, 255)


def test_긴_변을_2048px_이하로_줄이고_축소판은_400px이다() -> None:
    result = processor.sanitize(make_image((4000, 3000)))

    assert (result.width, result.height) == (MAX_LONG_SIDE, 1536)
    assert reopen(result.data).size == (MAX_LONG_SIDE, 1536)
    assert reopen(result.thumbnail).size == (THUMBNAIL_LONG_SIDE, 300)


def test_작은_사진은_키우지_않는다() -> None:
    result = processor.sanitize(make_image((100, 50)))
    assert reopen(result.data).size == (100, 50)
    assert reopen(result.thumbnail).size == (100, 50)


def test_세로가_긴_사진도_긴_변을_기준으로_줄인다() -> None:
    result = processor.sanitize(make_image((1000, 3000)))
    assert reopen(result.data).size == (683, MAX_LONG_SIDE)


@pytest.mark.parametrize(
    "raw",
    [b"", b"not an image", make_image()[:80], b"GIF89a" + b"\x00" * 20],
    ids=["빈 파일", "이미지 아님", "잘린 JPEG", "깨진 GIF"],
)
def test_깨진_파일은_InvalidImage(raw: bytes) -> None:
    with pytest.raises(InvalidImage):
        processor.sanitize(raw)


def test_지원하지_않는_형식은_InvalidImage() -> None:
    gif = io.BytesIO()
    Image.new("RGB", (4, 4)).save(gif, format="GIF")
    with pytest.raises(InvalidImage):
        processor.sanitize(gif.getvalue())


def test_결과에서_UTC_시각을_돌려준다() -> None:
    result = processor.sanitize(make_image(exif=make_exif()))
    assert result.captured_at is not None
    assert result.captured_at.tzinfo == UTC
