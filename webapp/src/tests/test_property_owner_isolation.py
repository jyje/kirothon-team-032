"""Property 18: 소유자 격리.

**Validates: Requirements 25.7**

모든 API 요청에 대해, 응답에 포함된 객체는 모두 요청한 소유자의 것이다. 소유자가 한 명뿐이어도
다른 `owner_id`의 데이터가 DB에 있을 수 있다고 보고 검사한다(다중 사용자 단계를 위한 속성).

임의의 데이터를 가진 소유자 세 명을 만들고 두 층에서 확인한다.
1. 서비스 층: 어느 소유자의 조회 결과에도 상대의 객체가 없고, 상대의 객체를 건드리면 `NotFound`다.
2. HTTP 층: 로그인한 소유자의 모든 응답 본문에 상대 데이터의 표식이 없고, 상대 ID는 404다.

이후 작업이 라우트를 더하면 `_http_probe`에 요청을 더해서 같은 속성으로 검사한다.
"""

from __future__ import annotations

import tempfile
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import Engine
from sqlmodel import Session

from open_attendee.config import Settings
from open_attendee.errors import NotFound
from open_attendee.main import create_app
from open_attendee.models import (
    Asset,
    AssetKind,
    Draft,
    Fact,
    LiveSummary,
    Sentence,
    SourceKind,
    SourceRef,
)
from open_attendee.sessions import SessionService
from open_attendee.storage import LocalBlobStore

from .conftest import BASE_URL, OWNER_HASH, SESSION_SECRET, login

ME = "owner"  # 로그인한 소유자(앱이 쓰는 고정 ID)
OTHERS = ("intruder-a", "intruder-b")
ALL_OWNERS = (ME, *OTHERS)
TAGS = {ME: "§MINE§", "intruder-a": "§OTHER§", "intruder-b": "§OTHER§"}
FOREIGN_TAG = "§OTHER§"  # `§`는 생성 글자(문자와 숫자)에 없어서 우연히 만들어지지 않는다

_letters = st.characters(whitelist_categories=("L", "N"))
_text = st.text(alphabet=_letters, min_size=0, max_size=20)
_title = st.text(alphabet=_letters, min_size=1, max_size=20)

session_spec = st.fixed_dictionaries(
    {
        "title": _title,
        "blocks": st.lists(_text, max_size=3),
        "assets": st.integers(min_value=0, max_value=3),
        "drafts": st.integers(min_value=0, max_value=2),
    }
)
world_spec = st.fixed_dictionaries(
    {owner: st.lists(session_spec, max_size=3) for owner in ALL_OWNERS}
).filter(lambda w: any(w[o] for o in OTHERS))


@dataclass
class Built:
    owner: str
    session_id: str
    title: str
    block_ids: list[str] = field(default_factory=list)
    assets: int = 0
    has_draft: bool = False


@dataclass
class World:
    client: TestClient
    engine: Engine
    blobs: LocalBlobStore
    by_owner: dict[str, list[Built]]

    @property
    def mine(self) -> list[Built]:
        return self.by_owner[ME]

    @property
    def foreign(self) -> list[Built]:
        return [b for owner in OTHERS for b in self.by_owner[owner]]

    def service(self, db: Session) -> SessionService:
        return SessionService(db, self.blobs)


def _populate(service: SessionService, db: Session, owner: str, spec: dict) -> Built:
    tag = TAGS[owner]
    created = service.create(owner, tag + spec["title"])
    built = Built(
        owner, created.id, tag + spec["title"], assets=spec["assets"], has_draft=spec["drafts"] > 0
    )
    for i, text in enumerate(spec["blocks"]):
        block_id = str(uuid.uuid4())
        service.save_block(owner, created.id, block_id, f"{tag}{i}{text}")
        built.block_ids.append(block_id)
    for i in range(spec["assets"]):
        db.add(
            Asset(
                session_id=created.id,
                kind=AssetKind.PHOTO,
                display_name=f"{tag}{i}.jpg",
                caption=f"{tag}설명{i}",
                mime="image/jpeg",
            )
        )
    for i in range(spec["drafts"]):
        draft = Draft(session_id=created.id, template_id="t", template_snapshot="{}")
        db.add(draft)
        sources = [SourceRef(kind=SourceKind.MEMO, target_id="m", locator=f"{tag}위치")]
        db.add(Fact(draft_id=draft.id, text=f"{tag}사실{i}", sources=sources))
        db.add(Sentence(draft_id=draft.id, section_id="s", text=f"{tag}문장{i}"))
    db.add(LiveSummary(session_id=created.id, bullets=[{"text": f"{tag}요약", "sources": []}]))
    db.commit()
    return built


@contextmanager
def _world(spec: dict) -> Iterator[World]:
    with tempfile.TemporaryDirectory() as tmp:
        config = Settings.from_env(
            {
                "OWNER_PASSWORD_HASH": OWNER_HASH,
                "SESSION_SECRET": SESSION_SECRET,
                "DATA_DIR": str(Path(tmp) / "data"),
            }
        )
        app = create_app(config, provider_factory=lambda: None)
        with TestClient(app, base_url=BASE_URL) as client:
            engine: Engine = client.app.state.engine  # type: ignore[attr-defined]
            blobs = LocalBlobStore(config.data_dir / "blobs")
            by_owner: dict[str, list[Built]] = {}
            with Session(engine) as db:
                service = SessionService(db, blobs)
                for owner in ALL_OWNERS:
                    by_owner[owner] = [_populate(service, db, owner, s) for s in spec[owner]]
            client.headers["X-CSRF-Token"] = login(client)
            yield World(client, engine, blobs, by_owner)


def _snapshot(world: World, owner: str) -> list[tuple[str, str, list[str]]]:
    """`owner`의 세션, 제목, 블록 글. 시도 전후에 같은지 비교한다."""
    with Session(world.engine) as db:
        service = world.service(db)
        return sorted(
            (
                item.session.id,
                item.session.title,
                [b.text for b in service.list_blocks(owner, item.session.id)],
            )
            for item in service.list(owner)
        )


def _forbidden_calls(
    service: SessionService, owner: str, foreign: Built
) -> list[Callable[[], object]]:
    """`owner`가 `foreign`(다른 소유자의 세션)에 하는 모든 동작. 전부 `NotFound`여야 한다."""
    calls: list[Callable[[], object]] = [
        lambda: service.get(owner, foreign.session_id),
        lambda: service.list_blocks(owner, foreign.session_id),
        lambda: service.update(owner, foreign.session_id, title="x"),
        lambda: service.save_block(owner, foreign.session_id, str(uuid.uuid4()), "x"),
        lambda: service.delete(owner, foreign.session_id),
    ]
    for block_id in foreign.block_ids:
        calls.append(lambda b=block_id: service.delete_block(owner, foreign.session_id, b))
        calls.append(lambda b=block_id: service.save_block(owner, foreign.session_id, b, "x"))
    return calls


def _check_service_layer(world: World) -> None:
    with Session(world.engine) as db:
        service = world.service(db)

        # 각 소유자의 조회 결과는 그 소유자의 객체뿐이다.
        for owner in ALL_OWNERS:
            built = {b.session_id: b for b in world.by_owner[owner]}
            items = service.list(owner)
            assert {i.session.id for i in items} == set(built)
            for item in items:
                assert item.session.owner_id == owner
                # 자료 수와 초안 상태는 자기 세션의 것만 센다.
                assert item.asset_count == built[item.session.id].assets
                assert (item.draft_status is not None) == built[item.session.id].has_draft
                blocks = service.list_blocks(owner, item.session.id)
                assert [b.id for b in blocks] == built[item.session.id].block_ids

        # 다른 소유자의 세션은 모든 동작에서 "없음"이다.
        for owner in ALL_OWNERS:
            others = [b for o in ALL_OWNERS if o != owner for b in world.by_owner[o]]
            for foreign in others:
                attempts = _forbidden_calls(service, owner, foreign)
                for attempt in attempts:
                    with pytest.raises(NotFound):
                        attempt()


def _check_http_layer(world: World) -> None:
    """로그인한 소유자가 부를 수 있는 모든 경로를 불러 응답에 상대 데이터가 없는지 본다."""
    client = world.client
    pages = [client.get("/sessions")] + [
        client.get(f"/sessions/{b.session_id}") for b in world.mine
    ]
    for page in pages:
        assert page.status_code == 200
        assert FOREIGN_TAG not in page.text
    for built in world.mine:
        assert built.title in pages[0].text

    for foreign in world.foreign:
        sid = foreign.session_id
        responses = [
            client.get(f"/sessions/{sid}"),
            client.patch(f"/sessions/{sid}", data={"title": "가로채기"}),
            client.put(f"/sessions/{sid}/blocks/{uuid.uuid4()}", data={"text": "끼워 넣기"}),
            client.delete(f"/sessions/{sid}"),
        ]
        for block_id in foreign.block_ids:
            responses.append(
                client.put(f"/sessions/{sid}/blocks/{block_id}", data={"text": "덮기"})
            )
            responses.append(client.delete(f"/sessions/{sid}/blocks/{block_id}"))
        for res in responses:
            assert res.status_code == 404
            assert FOREIGN_TAG not in res.text

    # 내 세션에서 상대의 블록 ID를 쓰려 해도 거부되고 응답에 상대 글이 나오지 않는다.
    if world.mine:
        target = world.mine[0].session_id
        for foreign in world.foreign:
            for block_id in foreign.block_ids:
                res = client.put(f"/sessions/{target}/blocks/{block_id}", data={"text": "x"})
                assert res.status_code == 422
                assert FOREIGN_TAG not in res.text


@settings(
    max_examples=30,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(spec=world_spec)
def test_property_18_owner_isolation(spec: dict) -> None:
    with _world(spec) as world:
        before = {owner: _snapshot(world, owner) for owner in OTHERS}

        _check_service_layer(world)
        _check_http_layer(world)

        # 어떤 시도도 상대의 데이터를 바꾸거나 지우지 못했다.
        assert {owner: _snapshot(world, owner) for owner in OTHERS} == before
