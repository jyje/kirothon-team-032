"""`PhotoProcessor`: 사진 정리(EXIF 제거, 회전, 축소)와 메모 연결(요구사항 3, 5).

위치 정보 보호가 이 모듈의 핵심이다. EXIF에서는 촬영 시각(`DateTimeOriginal`)과 그 시간대
(`OffsetTimeOriginal`) 두 값만 읽고 GPS 영역은 읽지도 저장하지도 않는다. 저장하는 이미지는 원본
객체를 복사하지 않고 픽셀 바이트로 새로 만든 이미지라서 메타데이터가 남을 길이 없다.
"""

from __future__ import annotations

import contextlib
import io
import math
import re
import warnings
from bisect import bisect_left
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone, tzinfo
from struct import error as struct_error
from typing import Final

import pillow_heif
from PIL import Image, ImageCms, ImageFile, ImageFilter, ImageOps, UnidentifiedImageError

from open_attendee.errors import ValidationFailed
from open_attendee.models import Asset, MemoBlock
from open_attendee.processors.face_detection import PhotoRegion

pillow_heif.register_heif_opener()

LINK_WINDOW: Final = timedelta(minutes=5)  # 사진과 메모를 같은 때로 보는 시간 차(요구사항 5.1)
MAX_LONG_SIDE: Final = 2048  # 저장하는 사진의 긴 변 상한(요구사항 3.7)
THUMBNAIL_LONG_SIDE: Final = 400  # 축소판의 긴 변
JPEG_QUALITY: Final = 88
THUMBNAIL_QUALITY: Final = 80

# EXIF 태그 번호. 읽는 것은 이 둘뿐이다.
_EXIF_IFD: Final = 0x8769
_TAG_DATETIME_ORIGINAL: Final = 0x9003
_TAG_OFFSET_TIME_ORIGINAL: Final = 0x9011

_EXIF_TIME_FORMAT: Final = "%Y:%m:%d %H:%M:%S"
_OFFSET_RE: Final = re.compile(r"([+-])(\d{2}):(\d{2})")
_MAX_OFFSET: Final = timedelta(hours=24)

_JPEG_FORMATS: Final = frozenset({"JPEG", "MPO"})  # MPO는 일부 휴대폰이 쓰는 JPEG 변형
_ACCEPTED_FORMATS: Final = _JPEG_FORMATS | {"PNG", "HEIF"}


class InvalidImage(ValidationFailed):
    """깨졌거나 읽을 수 없는 사진. 라우터가 422로 바꾼다(요구사항 3.8)."""


@dataclass(frozen=True)
class SanitizedPhoto:
    data: bytes  # EXIF가 없는 JPEG 또는 PNG
    thumbnail: bytes  # 긴 변 400px 이하 JPEG
    mime: str  # "image/jpeg" 또는 "image/png"
    width: int
    height: int
    captured_at: datetime | None  # UTC. EXIF에 시각이 없거나 읽을 수 없으면 None


def parse_exif_time(
    value: object, offset: object = None, default_tz: tzinfo = UTC
) -> datetime | None:
    """EXIF 촬영 시각 문자열을 UTC 시각으로 바꾼다. 읽을 수 없으면 `None`.

    EXIF 시각에는 보통 시간대가 없다. `OffsetTimeOriginal`(`+09:00` 형식)이 있으면 그것을 쓰고,
    없으면 `default_tz`로 해석한다. 기본값은 UTC다.
    """
    if not isinstance(value, str):
        return None
    try:
        naive = datetime.strptime(value.strip("\x00 "), _EXIF_TIME_FORMAT)
    except ValueError:
        return None
    zone = _parse_offset(offset) or default_tz
    return naive.replace(tzinfo=zone).astimezone(UTC)


def _parse_offset(value: object) -> tzinfo | None:
    if not isinstance(value, str):
        return None
    match = _OFFSET_RE.fullmatch(value.strip("\x00 "))
    if match is None:
        return None
    delta = timedelta(hours=int(match[2]), minutes=int(match[3]))
    if delta >= _MAX_OFFSET:
        return None
    return timezone(-delta if match[1] == "-" else delta)


def _read_captured_at(img: Image.Image, default_tz: tzinfo) -> datetime | None:
    """`DateTimeOriginal`과 `OffsetTimeOriginal`만 읽는다. GPS 영역에는 접근하지 않는다."""
    try:
        sub = img.getexif().get_ifd(_EXIF_IFD)
    except (OSError, SyntaxError, ValueError, KeyError, TypeError, AttributeError, struct_error):
        return None
    return parse_exif_time(
        sub.get(_TAG_DATETIME_ORIGINAL), sub.get(_TAG_OFFSET_TIME_ORIGINAL), default_tz
    )


class PhotoProcessor:
    def sanitize(self, raw: bytes, *, default_tz: tzinfo = UTC) -> SanitizedPhoto:
        """촬영 시각만 읽고 모든 EXIF를 지운 JPEG/PNG와 축소판을 돌려준다.

        - EXIF 회전을 픽셀에 반영한다(3.5). HEIC는 JPEG로 바꾸고, 긴 변을 2048px 이하로 줄인다.
        - 촬영 시각에 시간대가 없으면 `default_tz`로 해석한다(기본 UTC).
        - 깨진 파일이나 지원하지 않는 형식은 `InvalidImage`를 낸다.
        """
        try:
            return self._sanitize(raw, default_tz)
        except InvalidImage:
            raise
        except (
            UnidentifiedImageError,
            OSError,
            SyntaxError,
            ValueError,
            EOFError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
            MemoryError,
            struct_error,
        ) as exc:
            # 라이브러리 메시지에는 파일 내용이 섞일 수 있어서 종류만 남긴다.
            raise InvalidImage("사진 파일이 깨졌거나 읽을 수 없어요.") from exc

    def _sanitize(self, raw: bytes, default_tz: tzinfo) -> SanitizedPhoto:
        with warnings.catch_warnings():
            # 아주 큰 이미지는 경고 대신 오류로 거부한다.
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as probe:
                probe.verify()  # 헤더와 구조 검사. 픽셀 검사는 아래에서 load()가 한다.
            # verify() 뒤에는 같은 객체를 다시 쓸 수 없어서 새로 연다.
            with Image.open(io.BytesIO(raw)) as img:
                if img.format not in _ACCEPTED_FORMATS:
                    raise InvalidImage("JPEG, PNG, HEIC 사진만 올릴 수 있어요.")
                captured_at = _read_captured_at(img, default_tz)
                is_jpeg = img.format in _JPEG_FORMATS
                keep_png = img.format == "PNG"
                if is_jpeg:
                    # 디코딩 단계에서 미리 줄여 큰 사진의 메모리 사용을 낮춘다.
                    img.draft(img.mode, (MAX_LONG_SIDE, MAX_LONG_SIDE))
                with _truncation_is_error():
                    img.load()
                oriented = ImageOps.exif_transpose(img)  # 회전을 픽셀에 반영한 새 이미지
                oriented = _to_srgb(oriented)

        oriented.thumbnail((MAX_LONG_SIDE, MAX_LONG_SIDE), Image.Resampling.LANCZOS)
        main = _clean_copy(oriented, png=keep_png)
        return self._render(main, keep_png, captured_at)

    def blur(self, raw: bytes, regions: list[PhotoRegion]) -> SanitizedPhoto:
        with Image.open(io.BytesIO(raw)) as image:
            keep_png = image.format == "PNG"
            main = _clean_copy(image, png=keep_png)
        for region in regions:
            box = (
                math.floor(region.left * main.width),
                math.floor(region.top * main.height),
                math.ceil(region.right * main.width),
                math.ceil(region.bottom * main.height),
            )
            patch = main.crop(box)
            radius = max(6, max(patch.size) / 6)
            main.paste(patch.filter(ImageFilter.GaussianBlur(radius)), box)
        return self._render(main, keep_png, None)

    @staticmethod
    def _render(
        main: Image.Image,
        keep_png: bool,
        captured_at: datetime | None,
    ) -> SanitizedPhoto:
        data = _encode(main, png=keep_png)

        thumb_src = main.copy()
        thumb_src.thumbnail((THUMBNAIL_LONG_SIDE, THUMBNAIL_LONG_SIDE), Image.Resampling.LANCZOS)
        thumb = _encode(_clean_copy(thumb_src, png=False), png=False, quality=THUMBNAIL_QUALITY)
        return SanitizedPhoto(
            data=data,
            thumbnail=thumb,
            mime="image/png" if keep_png else "image/jpeg",
            width=main.width,
            height=main.height,
            captured_at=captured_at,
        )

    def link_photos(
        self, photos: Iterable[Asset], blocks: Iterable[MemoBlock], window: timedelta = LINK_WINDOW
    ) -> dict[str, str | None]:
        return link_photos(photos, blocks, window)


# ---------------------------------------------------------------------------- 사진과 메모 연결


def to_utc(moment: datetime) -> datetime:
    """UTC로 정규화한다. 시간대가 없는 시각은 UTC로 본다(요구사항 5.5)."""
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def link_photos(
    photos: Iterable[Asset], blocks: Iterable[MemoBlock], window: timedelta = LINK_WINDOW
) -> dict[str, str | None]:
    """사진마다 시각 차이가 가장 작은 메모 블록을 고른다. 결과는 `{사진 ID: 블록 ID 또는 None}`.

    - 기준 시각은 촬영 시각이고 없으면 업로드 시각이다. 모든 시각은 UTC로 맞춰 비교한다.
    - 차이가 `window` 이하인 블록만 후보다. 후보가 없으면 `None`.
    - 차이가 같으면 작성 시각이 앞선 블록을 고른다(시각까지 같으면 화면 순서가 앞선 블록).
    - 사용자가 직접 지정한 사진(`link_manual`)은 계산하지 않고 지금의 연결을 그대로 돌려준다.
    """
    ordered = sorted(blocks, key=lambda b: (to_utc(b.created_at), b.position, b.id))
    times = [to_utc(b.created_at) for b in ordered]
    result: dict[str, str | None] = {}
    for photo in photos:
        if photo.link_manual:
            result[photo.id] = photo.linked_block_id
            continue
        moment = to_utc(photo.captured_at or photo.created_at)
        right = bisect_left(times, moment)  # moment 이상인 첫 블록. 같은 시각 중 가장 앞선 블록
        candidates: list[int] = []
        if right < len(ordered):
            candidates.append(right)
        if right > 0:
            # moment보다 앞선 블록 중 가장 가까운 시각의 무리에서 가장 앞선 블록
            candidates.append(bisect_left(times, times[right - 1]))
        best: tuple[timedelta, int] | None = None
        for index in candidates:
            gap = abs(times[index] - moment)
            if gap <= window and (best is None or (gap, index) < best):
                best = (gap, index)
        result[photo.id] = ordered[best[1]].id if best else None
    return result


# ---------------------------------------------------------------------------- 이미지 도우미


@contextlib.contextmanager
def _truncation_is_error() -> Iterator[None]:
    """잘린 파일을 조용히 받아들이지 않도록 `LOAD_TRUNCATED_IMAGES`를 끈 채로 읽는다."""
    previous = ImageFile.LOAD_TRUNCATED_IMAGES
    ImageFile.LOAD_TRUNCATED_IMAGES = False
    try:
        yield
    finally:
        ImageFile.LOAD_TRUNCATED_IMAGES = previous


def _to_srgb(img: Image.Image) -> Image.Image:
    """ICC 프로필(예: 아이폰의 Display P3)이 있으면 sRGB로 바꿔, 프로필 없이도 색이 같게 한다."""
    profile = img.info.get("icc_profile")
    if not profile or img.mode not in {"RGB", "RGBA"}:
        return img
    try:
        source = ImageCms.ImageCmsProfile(io.BytesIO(profile))
        target = ImageCms.createProfile("sRGB")
        converted = ImageCms.profileToProfile(img, source, target, outputMode=img.mode)
    except (ImageCms.PyCMSError, OSError, ValueError):
        return img  # 변환하지 못해도 사진은 쓸 수 있다
    return converted if converted is not None else img


def _clean_copy(img: Image.Image, *, png: bool) -> Image.Image:
    """저장 형식에 맞는 모드로 바꾼 뒤 픽셀 바이트만으로 새 이미지를 만든다. 메타데이터가 없다."""
    if png:
        if img.mode not in {"RGB", "RGBA", "L", "LA"}:
            has_alpha = "transparency" in img.info or "A" in img.getbands()
            img = img.convert("RGBA" if has_alpha else "RGB")
    elif img.mode not in {"RGB", "L"}:
        if "A" in img.getbands() or "transparency" in img.info:
            rgba = img.convert("RGBA")
            background = Image.new("RGB", rgba.size, (255, 255, 255))
            background.paste(rgba, mask=rgba.getchannel("A"))  # 투명한 곳은 흰색
            img = background
        else:
            img = img.convert("RGB")
    return Image.frombytes(img.mode, img.size, img.tobytes())


def _encode(img: Image.Image, *, png: bool, quality: int = JPEG_QUALITY) -> bytes:
    out = io.BytesIO()
    if png:
        img.save(out, format="PNG", optimize=True)
    else:
        img.save(out, format="JPEG", quality=quality, optimize=True)
    return out.getvalue()
