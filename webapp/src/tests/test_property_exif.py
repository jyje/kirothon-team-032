"""Property 5: EXIF 제거.

**Validates: Requirements 3.3, 3.4**
"""

from __future__ import annotations

import io

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from PIL import ExifTags, Image

from open_attendee.models import Asset
from open_attendee.processors.photo import MAX_LONG_SIDE, PhotoProcessor
from tests.imaging import make_exif, make_image

_DEGREES = st.tuples(
    st.integers(0, 180).map(float), st.integers(0, 59).map(float), st.integers(0, 59).map(float)
)
_LOCATION_WORDS = ("gps", "lat", "lon", "location", "geo", "position_")


def test_Asset_모델에는_위치_정보_열이_없다() -> None:
    columns = {name.lower() for name in Asset.model_fields}
    assert not [c for c in columns if any(word in c for word in _LOCATION_WORDS)]
    assert not [c.name for c in Asset.__table__.columns if "gps" in c.name.lower()]  # type: ignore[attr-defined]


@settings(
    max_examples=60,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
@given(
    size=st.tuples(st.integers(1, 300), st.integers(1, 300)),
    fmt=st.sampled_from(["JPEG", "PNG", "HEIF"]),
    orientation=st.one_of(st.none(), st.integers(1, 8)),
    lat=_DEGREES,
    lon=_DEGREES,
    with_time=st.booleans(),
)
def test_sanitize_결과에는_EXIF가_없다(
    size: tuple[int, int],
    fmt: str,
    orientation: int | None,
    lat: tuple[float, float, float],
    lon: tuple[float, float, float],
    with_time: bool,
) -> None:
    exif = make_exif(
        captured="2026:11:14 10:30:00" if with_time else None,
        orientation=orientation,
        lat_lon=(lat, lon),
    )
    raw = make_image(size, fmt=fmt, exif=exif)
    assert len(Image.open(io.BytesIO(raw)).getexif()) > 0  # 입력에는 EXIF가 실제로 있다

    result = PhotoProcessor().sanitize(raw)

    for data in (result.data, result.thumbnail):
        reopened = Image.open(io.BytesIO(data))
        assert len(reopened.getexif()) == 0
        assert not reopened.getexif().get_ifd(ExifTags.IFD.GPSInfo)
        assert "exif" not in reopened.info
        assert b"Exif" not in data
    assert max(result.width, result.height) <= MAX_LONG_SIDE
    assert (result.captured_at is not None) == with_time
