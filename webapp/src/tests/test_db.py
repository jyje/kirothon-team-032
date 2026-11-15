"""DB 연결과 모델 저장 (요구사항 27.9, 25.7)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

import pytest
from sqlalchemy import Engine, inspect, text
from sqlmodel import Session, SQLModel

from open_attendee import models
from open_attendee.db import init_db, make_engine
from open_attendee.models import (
    Asset,
    AssetKind,
    AssetStatus,
    Fact,
    Job,
    JobKind,
    JobStatus,
    SourceKind,
    SourceRef,
    Template,
    TemplateSection,
)


def test_document_page_count_migration_preserves_existing_rows(engine: Engine) -> None:
    with Session(engine) as db:
        asset = Asset(
            session_id="legacy",
            kind=AssetKind.SLIDES,
            display_name="legacy.pdf",
            mime="application/pdf",
        )
        db.add(asset)
        db.commit()
        asset_id = asset.id

    with engine.begin() as conn:
        conn.exec_driver_sql("ALTER TABLE asset DROP COLUMN page_count")

    init_db(engine)
    init_db(engine)
    with Session(engine) as db:
        old = db.get(Asset, asset_id)
        assert old is not None
        assert old.display_name == "legacy.pdf"
        assert old.page_count is None


def test_wal_mode_and_busy_timeout(engine: Engine) -> None:
    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA journal_mode")).scalar_one() == "wal"
        assert conn.execute(text("PRAGMA busy_timeout")).scalar_one() > 0


def test_init_db_creates_all_tables_and_is_repeatable(engine: Engine) -> None:
    from open_attendee.db import init_db

    init_db(engine)  # 두 번째 호출도 오류 없이 끝난다.
    expected = {t.name for t in SQLModel.metadata.sorted_tables}
    assert {
        "eventsession",
        "memoblock",
        "asset",
        "consentrecord",
        "transcriptsegment",
        "docchunk",
        "fact",
        "sentence",
        "draft",
        "template",
        "job",
        "livesummary",
    } <= expected
    assert expected <= set(inspect(engine).get_table_names())


def test_asset_has_no_location_columns(engine: Engine) -> None:
    columns = {c["name"].lower() for c in inspect(engine).get_columns("asset")}
    assert not {c for c in columns if "gps" in c or "lat" in c or "lon" in c or "location" in c}
    assert "captured_at" in columns


def test_every_table_reaches_an_owner() -> None:
    """모든 테이블은 owner_id를 갖거나 session_id, asset_id, draft_id 사슬로 세션에 닿는다."""
    chain = {"session_id", "asset_id", "draft_id"}
    for table in SQLModel.metadata.sorted_tables:
        names = set(table.columns.keys())
        assert "owner_id" in names or names & chain, table.name


def test_json_and_datetime_columns_round_trip(engine: Engine) -> None:
    kst = timezone(timedelta(hours=9))
    taken = datetime(2026, 11, 14, 15, 0, tzinfo=kst)
    ref = SourceRef(kind=SourceKind.MEMO, target_id="b1", revision=2, locator="메모 1번째 블록")
    section = TemplateSection(id="s1", title="요약", instruction="쓰세요", max_sentences=3)
    with Session(engine) as db:
        asset = Asset(
            session_id="s",
            kind=AssetKind.PHOTO,
            display_name="a.jpg",
            mime="image/jpeg",
            captured_at=taken,
        )
        fact = Fact(draft_id="d", text="사실", sources=[ref])
        tpl = Template(name="블로그", output_kind="blog", sections=[section])
        job = Job(owner_id="o", session_id="s", kind=JobKind.SUMMARY, payload={"k": "v"})
        db.add_all([asset, fact, tpl, job])
        db.commit()
        ids = (asset.id, fact.id, tpl.id, job.id)

    with Session(engine) as db:
        asset, fact, tpl, job = (
            db.get(Asset, ids[0]),
            db.get(Fact, ids[1]),
            db.get(Template, ids[2]),
            db.get(Job, ids[3]),
        )
        assert asset is not None
        assert asset.captured_at == taken  # UTC로 저장해도 같은 시각이다.
        assert asset.captured_at is not None
        assert asset.captured_at.utcoffset() == timedelta(0)
        assert asset.status is AssetStatus.STORED
        assert fact is not None
        assert fact.sources == [ref]
        assert tpl is not None
        assert tpl.sections == [section]
        assert job is not None
        assert job.payload == {"k": "v"}
        assert job.status is JobStatus.QUEUED


def test_enums_are_stored_as_values_for_raw_sql(engine: Engine) -> None:
    with Session(engine) as db:
        db.add(Job(owner_id="o", session_id="s", kind=JobKind.DRAFT))
        db.commit()
    with engine.connect() as conn:
        row = conn.execute(text("SELECT kind, status FROM job")).one()
        assert tuple(row) == ("draft", "queued")
        queued = conn.execute(text("SELECT count(*) FROM job WHERE status='queued'")).scalar_one()
        assert queued == 1


def test_event_session_defaults(engine: Engine) -> None:
    with Session(engine) as db:
        s = models.EventSession(owner_id="o", title="행사", event_date=date(2026, 11, 14))
        db.add(s)
        db.commit()
        db.refresh(s)
        assert s.retain_audio is False
        assert len(s.id) == 32
        assert s.created_at.tzinfo is UTC


def test_delete_journal_mode_for_network_volumes(tmp_path) -> None:
    from sqlalchemy import text

    engine = make_engine(tmp_path / "x.sqlite3", journal_mode="delete")
    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA journal_mode")).scalar() == "delete"
    engine.dispose()


def test_unknown_journal_mode_is_rejected(tmp_path) -> None:
    with pytest.raises(ValueError):
        make_engine(tmp_path / "y.sqlite3", journal_mode="memory")
