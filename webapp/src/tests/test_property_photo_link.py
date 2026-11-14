"""Property 16: 사진 연결.

**Validates: Requirements 5.1, 5.2, 5.3**

`link_photos`의 결과를 모든 블록을 훑는 전수 탐색과 비교한다.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone, tzinfo

from hypothesis import given, settings
from hypothesis import strategies as st

from open_attendee.models import Asset, AssetKind, MemoBlock
from open_attendee.processors.photo import LINK_WINDOW, link_photos, to_utc

BASE = datetime(2026, 11, 14, 10, 0, tzinfo=UTC)
# 시간대가 없는 시각(UTC로 봄), UTC, 동쪽, 서쪽 시간대가 섞여도 같은 순간으로 비교해야 한다.
ZONES: list[tzinfo | None] = [
    None,
    UTC,
    timezone(timedelta(hours=9)),
    timezone(timedelta(hours=-5)),
]

seconds = st.integers(
    min_value=-900, max_value=900
)  # 겹치는 값이 자주 나와 동률 경우를 많이 만든다
zones = st.sampled_from(ZONES)


def moment(offset: int, zone: tzinfo | None) -> datetime:
    """`BASE + offset`초와 같은 순간을 `zone`의 시각으로 나타낸다."""
    instant = BASE + timedelta(seconds=offset)
    if zone is None:
        return instant.replace(tzinfo=None)  # 시간대 없는 UTC 시각
    return instant.astimezone(zone)


@st.composite
def blocks_strategy(draw) -> list[MemoBlock]:  # type: ignore[no-untyped-def]
    items = draw(st.lists(st.tuples(seconds, zones, st.integers(0, 5)), max_size=12))
    return [
        MemoBlock(id=f"b{i:02d}", session_id="s", position=pos, created_at=moment(sec, zone))
        for i, (sec, zone, pos) in enumerate(items)
    ]


@st.composite
def photos_strategy(draw) -> list[Asset]:  # type: ignore[no-untyped-def]
    photos = []
    for i in range(draw(st.integers(0, 8))):
        captured = draw(st.one_of(st.none(), st.tuples(seconds, zones)))
        uploaded = draw(st.tuples(seconds, zones))
        photos.append(
            Asset(
                id=f"p{i:02d}",
                session_id="s",
                kind=AssetKind.PHOTO,
                display_name="a.jpg",
                mime="image/jpeg",
                captured_at=moment(*captured) if captured else None,
                created_at=moment(*uploaded),
            )
        )
    return photos


def brute_force(photo: Asset, blocks: list[MemoBlock], window: timedelta) -> str | None:
    reference = to_utc(photo.captured_at or photo.created_at)
    near = [b for b in blocks if abs(to_utc(b.created_at) - reference) <= window]
    if not near:
        return None
    best = min(
        near,
        key=lambda b: (
            abs(to_utc(b.created_at) - reference),
            to_utc(b.created_at),
            b.position,
            b.id,
        ),
    )
    return best.id


@settings(max_examples=300, deadline=None)
@given(
    photos=photos_strategy(),
    blocks=blocks_strategy(),
    window=st.one_of(st.just(LINK_WINDOW), st.integers(0, 900).map(lambda s: timedelta(seconds=s))),
)
def test_link_photos는_전수_탐색_결과와_같다(
    photos: list[Asset], blocks: list[MemoBlock], window: timedelta
) -> None:
    result = link_photos(photos, blocks, window)

    assert set(result) == {p.id for p in photos}
    for photo in photos:
        assert result[photo.id] == brute_force(photo, blocks, window)


@settings(max_examples=200, deadline=None)
@given(photos=photos_strategy(), blocks=blocks_strategy())
def test_연결된_블록은_window_이하이고_더_가까운_블록은_없다(
    photos: list[Asset], blocks: list[MemoBlock]
) -> None:
    by_id = {b.id: b for b in blocks}
    result = link_photos(photos, blocks)
    for photo in photos:
        reference = to_utc(photo.captured_at or photo.created_at)
        chosen = result[photo.id]
        gaps = {b.id: abs(to_utc(b.created_at) - reference) for b in blocks}
        if chosen is None:
            assert all(gap > LINK_WINDOW for gap in gaps.values())
        else:
            assert gaps[chosen] <= LINK_WINDOW
            assert gaps[chosen] == min(gaps.values())
            assert chosen in by_id


@settings(max_examples=100, deadline=None)
@given(photos=photos_strategy(), blocks=blocks_strategy(), pinned=st.sampled_from([None, "b00"]))
def test_수동으로_지정한_연결은_바꾸지_않는다(
    photos: list[Asset], blocks: list[MemoBlock], pinned: str | None
) -> None:
    for photo in photos:
        photo.link_manual = True
        photo.linked_block_id = pinned
    assert link_photos(photos, blocks) == {p.id: pinned for p in photos}
