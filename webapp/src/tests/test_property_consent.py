"""Property 2(동의 범위)와 Property 3(혼자 한 음성 메모 예외).

**Validates: Requirements 9.1, 9.2, 9.4, 10.1, 10.2, 10.3**

임의의 자료 종류, `solo_voice`, 동의 기록 조합(다른 세션, 철회됨, 체크 누락, 없는 기록)으로
`needs_consent`와 `require_consent`를 확인한다. 두 속성은 각각 별도 테스트 함수다.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy import Engine
from sqlmodel import Session

from open_attendee.consent import ConsentGate
from open_attendee.db import init_db, make_engine
from open_attendee.errors import ConsentRequired
from open_attendee.models import Asset, AssetKind, ConsentRecord, utcnow

SESSION = "session-a"
OTHER_SESSION = "session-b"

AUDIO_AND_OTHER_KINDS = st.sampled_from(list(AssetKind))


@pytest.fixture(scope="module")
def shared_engine(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Engine]:
    path: Path = tmp_path_factory.mktemp("consent-prop") / "db.sqlite3"
    engine = make_engine(path)
    init_db(engine)
    yield engine
    engine.dispose()


record_specs = st.fixed_dictionaries(
    {
        "same_session": st.booleans(),
        "revoked": st.booleans(),
        "informed_all": st.booleans(),
        "can_document": st.booleans(),
        "no_outside_disclosure": st.booleans(),
    }
)
# 자료가 가리키는 기록: 없음, 존재하지 않는 ID, 만든 기록 중 하나
pointers = st.one_of(st.none(), st.just("missing"), st.integers(min_value=0, max_value=3))


def _is_valid(spec: dict[str, bool]) -> bool:
    return (
        spec["same_session"]
        and not spec["revoked"]
        and spec["informed_all"]
        and spec["can_document"]
        and spec["no_outside_disclosure"]
    )


def _store(db: Session, specs: list[dict[str, bool]]) -> list[ConsentRecord]:
    records = []
    for spec in specs:
        record = ConsentRecord(
            id=uuid.uuid4().hex,
            session_id=SESSION if spec["same_session"] else OTHER_SESSION,
            informed_all=spec["informed_all"],
            can_document=spec["can_document"],
            no_outside_disclosure=spec["no_outside_disclosure"],
            obtained_on=date(2026, 11, 14),
            method="구두 공지",
            revoked_at=utcnow() if spec["revoked"] else None,
        )
        db.add(record)
        records.append(record)
    db.commit()
    return records


def _pointed_id(pointer: str | int | None, records: list[ConsentRecord]) -> str | None:
    if pointer is None:
        return None
    if pointer == "missing":
        return uuid.uuid4().hex
    return records[pointer % len(records)].id if records else None


@settings(max_examples=150, deadline=None)
@given(
    kind=AUDIO_AND_OTHER_KINDS,
    solo_voice=st.booleans(),
    specs=st.lists(record_specs, max_size=4),
    pointer=pointers,
)
def test_property_2_consent_scope(
    shared_engine: Engine,
    kind: AssetKind,
    solo_voice: bool,
    specs: list[dict[str, bool]],
    pointer: str | int | None,
) -> None:
    """동의로 인정된 기록은 항상 같은 세션이고 철회되지 않았고 세 항목이 모두 참이다."""
    with Session(shared_engine) as db:
        records = _store(db, specs)
        consent_id = _pointed_id(pointer, records)
        asset = Asset(
            session_id=SESSION,
            kind=kind,
            display_name="a",
            mime="audio/webm",
            solo_voice=solo_voice,
            consent_id=consent_id,
        )
        gate = ConsentGate(db)
        try:
            accepted = gate.require_consent(asset)
        except ConsentRequired:
            # 거부되었다면 동의가 필요한 자료이고, 가리킨 기록은 유효하지 않다.
            assert gate.needs_consent(asset)
            by_id = {r.id: spec for r, spec in zip(records, specs, strict=True)}
            assert consent_id is None or consent_id not in by_id or not _is_valid(by_id[consent_id])
            return
        if accepted is None:
            assert not gate.needs_consent(asset)
            return
        assert accepted.id == consent_id
        assert accepted.session_id == asset.session_id
        assert accepted.revoked_at is None
        assert accepted.informed_all
        assert accepted.can_document
        assert accepted.no_outside_disclosure


@settings(max_examples=100, deadline=None)
@given(kind=AUDIO_AND_OTHER_KINDS, solo_voice=st.booleans())
def test_property_3_solo_voice_memo_exception(kind: AssetKind, solo_voice: bool) -> None:
    """동의 없이 처리되는 자료는 `solo_voice=True`인 음성 메모와 오디오가 아닌 자료뿐이다."""
    gate = ConsentGate(db=None)  # type: ignore[arg-type]  # needs_consent는 DB를 쓰지 않는다
    asset = Asset(session_id=SESSION, kind=kind, display_name="a", mime="x", solo_voice=solo_voice)
    needs = gate.needs_consent(asset)
    if kind == AssetKind.RECORDING:
        assert needs  # 녹음은 solo_voice와 상관없이 동의가 필요하다
    elif kind == AssetKind.VOICE_MEMO:
        assert needs == (not solo_voice)
    else:
        assert not needs  # 사진, 발표자료, 참고자료
