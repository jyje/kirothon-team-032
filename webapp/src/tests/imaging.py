"""테스트용 이미지 만들기. GPS가 든 EXIF를 붙인 JPEG, PNG, HEIC 바이트를 돌려준다."""

from __future__ import annotations

import io
from datetime import UTC, datetime

import pillow_heif
from PIL import ExifTags, Image

pillow_heif.register_heif_opener()

GPS = ((37.0, 33.0, 10.0), (127.0, 1.0, 2.0))  # 위도, 경도(도, 분, 초)


def make_exif(
    *,
    captured: str | None = "2026:11:14 10:30:00",
    offset: str | None = None,
    orientation: int | None = None,
    gps: bool = True,
    lat_lon: tuple[tuple[float, float, float], tuple[float, float, float]] = GPS,
) -> Image.Exif:
    exif = Image.Exif()
    exif[0x010F] = "TestCam"  # Make
    if orientation is not None:
        exif[0x0112] = orientation
    sub = exif.get_ifd(ExifTags.IFD.Exif)
    if captured is not None:
        sub[0x9003] = captured
    if offset is not None:
        sub[0x9011] = offset
    if gps:
        info = exif.get_ifd(ExifTags.IFD.GPSInfo)
        info[1], info[2] = "N", lat_lon[0]
        info[3], info[4] = "E", lat_lon[1]
    return exif


def make_image(
    size: tuple[int, int] = (64, 32),
    *,
    fmt: str = "JPEG",
    mode: str = "RGB",
    color: object = (200, 30, 30),
    exif: Image.Exif | None = None,
) -> bytes:
    image = Image.new(mode, size, color)  # type: ignore[arg-type]
    out = io.BytesIO()
    kwargs = {"exif": exif} if exif is not None else {}
    image.save(out, format=fmt, **kwargs)
    return out.getvalue()


def make_split_image(size: tuple[int, int], exif: Image.Exif) -> bytes:
    """왼쪽 절반은 빨강, 오른쪽 절반은 파랑인 JPEG. 회전이 반영됐는지 확인할 때 쓴다."""
    image = Image.new("RGB", size, (0, 0, 255))
    image.paste((255, 0, 0), (0, 0, size[0] // 2, size[1]))
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=95, exif=exif)
    return out.getvalue()


def utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)
