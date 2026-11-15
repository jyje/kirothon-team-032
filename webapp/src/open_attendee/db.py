"""SQLite 연결. 저널 모드(기본 WAL)와 busy_timeout을 켜고 테이블을 만드는 초기화 함수를 둔다."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, event
from sqlmodel import Session, SQLModel, create_engine

BUSY_TIMEOUT_MS = 5000


JOURNAL_MODES = ("wal", "delete")


def _pragma_setter(journal_mode: str):
    def _set_pragmas(dbapi_connection: sqlite3.Connection, _record: object) -> None:
        cursor = dbapi_connection.cursor()
        try:
            # 쓰기 주체가 앱 하나라서 WAL로 읽기와 쓰기가 서로 막지 않게 한다(요구사항 27.9).
            # NFS 같은 네트워크 볼륨은 WAL이 쓰는 공유 메모리 파일을 믿을 수 없어 delete로 쓴다.
            cursor.execute(f"PRAGMA journal_mode={journal_mode}")
            cursor.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
            cursor.execute("PRAGMA synchronous=NORMAL")
        finally:
            cursor.close()

    return _set_pragmas


def make_engine(db_path: Path | str, journal_mode: str = "wal") -> Engine:
    """`db_path`의 SQLite 파일을 여는 엔진을 만든다. 부모 디렉터리가 없으면 만든다."""
    if journal_mode not in JOURNAL_MODES:
        raise ValueError(f"journal_mode는 {JOURNAL_MODES} 중 하나여야 해요")
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{path}",
        # 요청 스레드와 워커 스레드가 같은 엔진을 쓴다.
        connect_args={"check_same_thread": False},
    )
    event.listen(engine, "connect", _pragma_setter(journal_mode))
    return engine


def init_db(engine: Engine) -> None:
    """모든 테이블을 만든다. 이미 있으면 건드리지 않는다."""
    from open_attendee import models  # noqa: F401  테이블을 SQLModel.metadata에 등록한다.

    # 기존 자료는 보존하고 새 열만 추가한다.
    with engine.begin() as conn:
        conn.exec_driver_sql("BEGIN IMMEDIATE")
        columns = {column[1] for column in conn.exec_driver_sql("PRAGMA table_info(asset)")}
        if columns and "page_count" not in columns:
            conn.exec_driver_sql("ALTER TABLE asset ADD COLUMN page_count INTEGER")
    SQLModel.metadata.create_all(engine)


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    """한 작업 단위. 예외 없이 끝나면 커밋하고, 예외가 나면 되돌린다."""
    with Session(engine) as session:
        try:
            yield session
            session.commit()
        except BaseException:
            session.rollback()
            raise
