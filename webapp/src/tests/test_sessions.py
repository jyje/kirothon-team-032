"""세션과 메모 블록 단위 테스트 (요구사항 1.1, 1.2, 1.4, 1.5, 2.1~2.5)."""

from __future__ import annotations

import io
import threading
import uuid
from datetime import date

import pytest
from sqlalchemy import Engine, func
from sqlmodel import Session, select

from open_attendee.errors import NotFound, ValidationFailed
from open_attendee.models import (
    Asset,
    AssetKind,
    ConsentRecord,
    DocChunk,
    Draft,
    EventSession,
    Fact,
    Job,
    JobKind,
    LiveSummary,
    MemoBlock,
    Sentence,
    SourceKind,
    SourceRef,
    TranscriptSegment,
)
from open_attendee.sessions import SessionService
from open_attendee.storage import BlobNotFound, LocalBlobStore, make_key

OWNER = "owner"
OTHER = "someone-else"


def new_block_id() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------- 세션 만들기 (1.1, 1.2)


def test_create_stores_session_for_owner(sessions: SessionService) -> None:
    created = sessions.create(OWNER, "AWSKRUG 밋업", date(2026, 11, 14))
    assert created.owner_id == OWNER
    assert created.title == "AWSKRUG 밋업"
    assert created.event_date == date(2026, 11, 14)
    assert created.retain_audio is False
    assert [item.session.id for item in sessions.list(OWNER)] == [created.id]


@pytest.mark.parametrize("title", ["a", "가", "x" * 200])
def test_create_accepts_titles_of_1_to_200_chars(sessions: SessionService, title: str) -> None:
    assert sessions.create(OWNER, title).title == title


@pytest.mark.parametrize("title", ["", "   ", "\n\t", "x" * 201, "가" * 201])
def test_create_rejects_empty_or_too_long_titles(sessions: SessionService, title: str) -> None:
    with pytest.raises(ValidationFailed):
        sessions.create(OWNER, title)
    assert sessions.list(OWNER) == []


def test_create_trims_surrounding_spaces(sessions: SessionService) -> None:
    assert sessions.create(OWNER, "  밋업  ").title == "밋업"


# ---------------------------------------------------------------- 수정 (1.4)


def test_update_changes_title_and_date_and_touches_updated_at(sessions: SessionService) -> None:
    created = sessions.create(OWNER, "처음", date(2026, 1, 1))
    before = created.updated_at
    updated = sessions.update(OWNER, created.id, title="바뀐 제목", event_date=date(2026, 2, 2))
    assert updated.title == "바뀐 제목"
    assert updated.event_date == date(2026, 2, 2)
    assert updated.updated_at > before
    assert updated.created_at == created.created_at


def test_update_without_event_date_keeps_it_and_none_clears_it(sessions: SessionService) -> None:
    created = sessions.create(OWNER, "제목", date(2026, 1, 1))
    assert sessions.update(OWNER, created.id, title="새 제목").event_date == date(2026, 1, 1)
    assert sessions.update(OWNER, created.id, event_date=None).event_date is None


def test_update_with_invalid_title_changes_nothing(sessions: SessionService) -> None:
    created = sessions.create(OWNER, "제목")
    with pytest.raises(ValidationFailed):
        sessions.update(OWNER, created.id, title="")
    assert sessions.get(OWNER, created.id).title == "제목"


def test_update_unknown_or_foreign_session_is_not_found(sessions: SessionService) -> None:
    foreign = sessions.create(OTHER, "남의 세션")
    with pytest.raises(NotFound):
        sessions.update(OWNER, foreign.id, title="가로채기")
    with pytest.raises(NotFound):
        sessions.update(OWNER, "missing", title="x")
    assert sessions.get(OTHER, foreign.id).title == "남의 세션"


# ---------------------------------------------------------------- 삭제 (1.5)


def _populate(db: Session, blobs: LocalBlobStore, session_id: str, owner: str = OWNER) -> list[str]:
    """세션에 모든 종류의 하위 행과 파일을 채운다. 만든 Blob 키를 돌려준다."""
    keys: list[str] = []
    asset_ids: list[str] = []
    for kind in (AssetKind.PHOTO, AssetKind.SLIDES):
        asset = Asset(session_id=session_id, kind=kind, display_name="f", mime="x/y")
        asset.blob_key = make_key(owner, session_id, asset.id)
        blobs.put(asset.blob_key, io.BytesIO(b"data"))
        keys.append(asset.blob_key)
        db.add(asset)
        asset_ids.append(asset.id)
    # 파생 파일(축소판)처럼 Asset 행이 직접 가리키지 않는 파일도 함께 지워져야 한다.
    thumb = make_key(owner, session_id, asset_ids[0] + ".thumb")
    blobs.put(thumb, io.BytesIO(b"thumb"))
    keys.append(thumb)

    db.add(DocChunk(asset_id=asset_ids[1], page=1, text="쪽"))
    db.add(TranscriptSegment(asset_id=asset_ids[0], start_ms=0, end_ms=10, text="말"))
    db.add(MemoBlock(id=new_block_id(), session_id=session_id, text="메모"))
    db.add(
        ConsentRecord(
            session_id=session_id,
            informed_all=True,
            can_document=True,
            no_outside_disclosure=True,
            obtained_on=date(2026, 11, 14),
            method="구두",
        )
    )
    draft = Draft(session_id=session_id, template_id="t", template_snapshot="{}")
    db.add(draft)
    db.add(
        Fact(
            draft_id=draft.id,
            text="사실",
            sources=[SourceRef(kind=SourceKind.MEMO, target_id="m", locator="메모")],
        )
    )
    db.add(Sentence(draft_id=draft.id, section_id="s", text="문장"))
    db.add(LiveSummary(session_id=session_id, bullets=[]))
    db.add(Job(owner_id=owner, session_id=session_id, kind=JobKind.SUMMARY))
    db.commit()
    return keys


def _row_counts(db: Session) -> dict[str, int]:
    tables = (
        EventSession,
        MemoBlock,
        Asset,
        ConsentRecord,
        TranscriptSegment,
        DocChunk,
        Fact,
        Sentence,
        Draft,
        Job,
        LiveSummary,
    )
    return {t.__name__: db.exec(select(func.count()).select_from(t)).one() for t in tables}


def test_delete_removes_every_row_and_file_of_the_session(
    sessions: SessionService, db: Session, blobs: LocalBlobStore
) -> None:
    target = sessions.create(OWNER, "지울 세션")
    keys = _populate(db, blobs, target.id)
    assert all(count >= 1 for count in _row_counts(db).values())

    sessions.delete(OWNER, target.id)

    assert _row_counts(db) == {name: 0 for name in _row_counts(db)}
    for key in keys:
        with pytest.raises(BlobNotFound):
            blobs.open(key)
    with pytest.raises(NotFound):
        sessions.get(OWNER, target.id)


def test_delete_leaves_other_sessions_untouched(
    sessions: SessionService, db: Session, blobs: LocalBlobStore
) -> None:
    gone = sessions.create(OWNER, "지움")
    kept = sessions.create(OWNER, "남김")
    foreign = sessions.create(OTHER, "남의 것")
    _populate(db, blobs, gone.id)
    kept_keys = _populate(db, blobs, kept.id)
    foreign_keys = _populate(db, blobs, foreign.id, owner=OTHER)
    before = _row_counts(db)

    sessions.delete(OWNER, gone.id)

    after = _row_counts(db)
    for name, count in after.items():
        # 세 세션이 같은 수의 하위 행을 가졌으므로 하나가 빠지면 3분의 1이 줄어든다.
        assert count == before[name] - before[name] // 3, name
    for key in kept_keys + foreign_keys:
        with blobs.open(key) as f:
            assert f.read()
    assert {item.session.id for item in sessions.list(OWNER)} == {kept.id}


def test_delete_foreign_session_is_not_found_and_changes_nothing(
    sessions: SessionService, db: Session, blobs: LocalBlobStore
) -> None:
    foreign = sessions.create(OTHER, "남의 것")
    keys = _populate(db, blobs, foreign.id, owner=OTHER)
    with pytest.raises(NotFound):
        sessions.delete(OWNER, foreign.id)
    assert sessions.get(OTHER, foreign.id).title == "남의 것"
    for key in keys:
        with blobs.open(key) as f:
            assert f.read()


def test_failed_file_deletion_keeps_db_rows_so_delete_can_be_retried(
    sessions: SessionService, db: Session, blobs: LocalBlobStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = sessions.create(OWNER, "재시도")
    _populate(db, blobs, target.id)

    def boom(_prefix: str) -> None:
        raise OSError("disk error")

    monkeypatch.setattr(blobs, "delete_prefix", boom)
    with pytest.raises(OSError, match="disk error"):
        sessions.delete(OWNER, target.id)
    assert sessions.get(OWNER, target.id).title == "재시도"

    monkeypatch.undo()
    sessions.delete(OWNER, target.id)
    with pytest.raises(NotFound):
        sessions.get(OWNER, target.id)


# ---------------------------------------------------------------- 목록 (1.3의 데이터)


def test_list_shows_asset_count_and_latest_draft_status(
    sessions: SessionService, db: Session
) -> None:
    with_stuff = sessions.create(OWNER, "자료 있음", date(2026, 11, 14))
    empty = sessions.create(OWNER, "비어 있음", date(2026, 11, 1))
    for _ in range(3):
        db.add(Asset(session_id=with_stuff.id, kind=AssetKind.PHOTO, display_name="p", mime="i/j"))
    db.add(Draft(session_id=with_stuff.id, template_id="t", template_snapshot="{}"))
    db.commit()
    db.add(
        Draft(
            session_id=with_stuff.id,
            template_id="t",
            template_snapshot="{}",
            status="in_review",
        )
    )
    db.commit()

    items = {item.session.id: item for item in sessions.list(OWNER)}
    assert items[with_stuff.id].asset_count == 3
    assert items[with_stuff.id].draft_status == "in_review"
    assert items[empty.id].asset_count == 0
    assert items[empty.id].draft_status is None


def test_list_orders_by_event_date_desc_with_undated_last(sessions: SessionService) -> None:
    old = sessions.create(OWNER, "옛날", date(2026, 1, 1))
    new = sessions.create(OWNER, "최근", date(2026, 12, 1))
    undated = sessions.create(OWNER, "날짜 없음")
    assert [i.session.id for i in sessions.list(OWNER)] == [new.id, old.id, undated.id]


def test_list_only_shows_own_sessions(sessions: SessionService) -> None:
    mine = sessions.create(OWNER, "내 것")
    sessions.create(OTHER, "남의 것")
    assert [i.session.id for i in sessions.list(OWNER)] == [mine.id]


# ---------------------------------------------------------------- 메모 블록 (2.1~2.5)


def test_first_save_uses_client_uuid_and_revision_1(sessions: SessionService) -> None:
    s = sessions.create(OWNER, "세션")
    block_id = new_block_id()
    block = sessions.save_block(OWNER, s.id, block_id, "첫 메모")
    assert block.id == block_id
    assert block.revision == 1
    assert block.text == "첫 메모"
    assert block.session_id == s.id


def test_each_resave_raises_revision_by_exactly_one(sessions: SessionService) -> None:
    s = sessions.create(OWNER, "세션")
    block_id = new_block_id()
    revisions = [sessions.save_block(OWNER, s.id, block_id, f"v{i}").revision for i in range(6)]
    assert revisions == [1, 2, 3, 4, 5, 6]
    saved = sessions.list_blocks(OWNER, s.id)
    assert len(saved) == 1
    assert saved[0].text == "v5"
    assert saved[0].updated_at >= saved[0].created_at


def test_resave_with_same_text_still_raises_revision(sessions: SessionService) -> None:
    s = sessions.create(OWNER, "세션")
    block_id = new_block_id()
    sessions.save_block(OWNER, s.id, block_id, "같은 글")
    assert sessions.save_block(OWNER, s.id, block_id, "같은 글").revision == 2


def test_uuid_forms_map_to_the_same_block(sessions: SessionService) -> None:
    s = sessions.create(OWNER, "세션")
    raw = uuid.uuid4()
    first = sessions.save_block(OWNER, s.id, raw.hex, "a")
    second = sessions.save_block(OWNER, s.id, str(raw).upper(), "b")
    assert first.id == second.id == str(raw)
    assert second.revision == 2


@pytest.mark.parametrize("bad_id", ["", "not-a-uuid", "../../etc", "123", "g" * 32])
def test_non_uuid_block_ids_are_rejected(sessions: SessionService, bad_id: str) -> None:
    s = sessions.create(OWNER, "세션")
    with pytest.raises(ValidationFailed):
        sessions.save_block(OWNER, s.id, bad_id, "x")
    assert sessions.list_blocks(OWNER, s.id) == []


def test_text_of_exactly_10000_chars_is_accepted_and_10001_is_rejected(
    sessions: SessionService,
) -> None:
    s = sessions.create(OWNER, "세션")
    block_id = new_block_id()
    assert sessions.save_block(OWNER, s.id, block_id, "가" * 10_000).revision == 1
    with pytest.raises(ValidationFailed):
        sessions.save_block(OWNER, s.id, block_id, "가" * 10_001)
    saved = sessions.list_blocks(OWNER, s.id)[0]
    assert saved.revision == 1  # 거부된 저장은 revision을 올리지 않는다
    assert len(saved.text) == 10_000


def test_oversized_first_save_creates_no_block(sessions: SessionService) -> None:
    s = sessions.create(OWNER, "세션")
    with pytest.raises(ValidationFailed):
        sessions.save_block(OWNER, s.id, new_block_id(), "x" * 10_001)
    assert sessions.list_blocks(OWNER, s.id) == []


def test_empty_text_is_allowed(sessions: SessionService) -> None:
    s = sessions.create(OWNER, "세션")
    assert sessions.save_block(OWNER, s.id, new_block_id(), "").text == ""


def test_more_than_20_blocks_are_allowed_and_keep_order(sessions: SessionService) -> None:
    s = sessions.create(OWNER, "세션")
    ids = [new_block_id() for _ in range(25)]
    for i, block_id in enumerate(ids):
        sessions.save_block(OWNER, s.id, block_id, f"메모 {i}")
    blocks = sessions.list_blocks(OWNER, s.id)
    assert [b.id for b in blocks] == ids
    assert [b.position for b in blocks] == list(range(25))


def test_resave_keeps_position_unless_given(sessions: SessionService) -> None:
    s = sessions.create(OWNER, "세션")
    a, b = new_block_id(), new_block_id()
    sessions.save_block(OWNER, s.id, a, "a")
    sessions.save_block(OWNER, s.id, b, "b")
    sessions.save_block(OWNER, s.id, a, "a2")
    assert [x.id for x in sessions.list_blocks(OWNER, s.id)] == [a, b]
    sessions.save_block(OWNER, s.id, a, "a3", position=5)
    assert [x.id for x in sessions.list_blocks(OWNER, s.id)] == [b, a]


def test_delete_block_removes_it_and_unlinks_photos(sessions: SessionService, db: Session) -> None:
    s = sessions.create(OWNER, "세션")
    block_id = new_block_id()
    sessions.save_block(OWNER, s.id, block_id, "메모")
    photo = Asset(
        session_id=s.id,
        kind=AssetKind.PHOTO,
        display_name="p",
        mime="i/j",
        linked_block_id=block_id,
        link_manual=True,
    )
    db.add(photo)
    db.commit()

    sessions.delete_block(OWNER, s.id, block_id)

    assert sessions.list_blocks(OWNER, s.id) == []
    db.refresh(photo)
    assert photo.linked_block_id is None
    assert photo.link_manual is False
    with pytest.raises(NotFound):
        sessions.delete_block(OWNER, s.id, block_id)


def test_block_id_used_by_another_session_is_rejected(sessions: SessionService) -> None:
    first = sessions.create(OWNER, "하나")
    second = sessions.create(OWNER, "둘")
    block_id = new_block_id()
    sessions.save_block(OWNER, first.id, block_id, "원래")
    with pytest.raises(ValidationFailed):
        sessions.save_block(OWNER, second.id, block_id, "덮어쓰기")
    with pytest.raises(NotFound):
        sessions.delete_block(OWNER, second.id, block_id)
    assert sessions.list_blocks(OWNER, first.id)[0].text == "원래"


def test_block_operations_on_foreign_session_are_not_found(sessions: SessionService) -> None:
    foreign = sessions.create(OTHER, "남의 세션")
    block_id = new_block_id()
    sessions.save_block(OTHER, foreign.id, block_id, "비밀 메모")
    with pytest.raises(NotFound):
        sessions.save_block(OWNER, foreign.id, block_id, "덮어쓰기")
    with pytest.raises(NotFound):
        sessions.delete_block(OWNER, foreign.id, block_id)
    with pytest.raises(NotFound):
        sessions.list_blocks(OWNER, foreign.id)
    assert sessions.list_blocks(OTHER, foreign.id)[0].text == "비밀 메모"


def test_concurrent_saves_raise_revision_exactly_once_each(
    engine: Engine, blobs: LocalBlobStore
) -> None:
    with Session(engine) as setup_db:
        setup = SessionService(setup_db, blobs)
        session_id = setup.create(OWNER, "동시 저장").id
        block_id = new_block_id()
        setup.save_block(OWNER, session_id, block_id, "시작")

    workers, saves = 6, 5
    errors: list[BaseException] = []

    def work() -> None:
        try:
            with Session(engine) as worker_db:
                service = SessionService(worker_db, blobs)
                for i in range(saves):
                    service.save_block(OWNER, session_id, block_id, f"글 {i}")
        except BaseException as exc:  # noqa: BLE001  스레드 밖에서 확인하려고 모은다
            errors.append(exc)

    threads = [threading.Thread(target=work) for _ in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    with Session(engine) as check_db:
        block = SessionService(check_db, blobs).list_blocks(OWNER, session_id)[0]
    assert block.revision == 1 + workers * saves


def test_concurrent_first_saves_of_one_id_create_one_block(
    engine: Engine, blobs: LocalBlobStore
) -> None:
    with Session(engine) as setup_db:
        session_id = SessionService(setup_db, blobs).create(OWNER, "동시 첫 저장").id
    block_id = new_block_id()
    barrier = threading.Barrier(4)
    errors: list[BaseException] = []

    def work() -> None:
        try:
            with Session(engine) as worker_db:
                service = SessionService(worker_db, blobs)
                barrier.wait()
                service.save_block(OWNER, session_id, block_id, "같은 블록")
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=work) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    with Session(engine) as check_db:
        blocks = SessionService(check_db, blobs).list_blocks(OWNER, session_id)
    assert len(blocks) == 1
    assert blocks[0].revision == 4
