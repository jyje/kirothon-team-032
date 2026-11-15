"""파일 저장소. 로컬 볼륨과 S3에서 공통 키 규칙을 사용한다.

키는 `<owner>/<session>/<asset_uuid>` 형식이다. 원래 파일 이름은 키에 쓰지 않는다(요구사항 8.4).
키에 경로를 벗어나는 문자(`..`, 절대 경로, 구분자 오용)가 있으면 파일을 건드리기 전에 거부한다.
"""

from __future__ import annotations

import contextlib
import errno
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import BinaryIO, Protocol

# 키의 각 구간. 첫 글자는 영문, 숫자, 밑줄이라서 `.`과 `..`이 통과하지 못한다.
_SEGMENT_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*")
KEY_SEGMENTS = 3
_COPY_CHUNK = 1024 * 1024
# 디스크 공간이나 할당량 부족을 뜻하는 OS 오류 번호.
_FULL_ERRNOS = frozenset({errno.ENOSPC, errno.EDQUOT})


class InvalidBlobKey(ValueError):
    """키 형식이 맞지 않거나 경로를 벗어나려 한다."""


class BlobNotFound(FileNotFoundError):
    """해당 키의 파일이 없다."""


class StorageFull(OSError):
    """저장소에 쓸 공간이 없다. 호출한 쪽이 507로 바꾼다."""


class StorageUnavailable(OSError):
    """첨부 저장소 요청을 완료하지 못했다."""


class BlobStore(Protocol):
    def put(self, key: str, data: BinaryIO) -> int:
        """`data`를 읽어 저장하고 저장한 바이트 수를 돌려준다."""
        ...

    def open(self, key: str) -> BinaryIO: ...

    def delete(self, key: str) -> None:
        """파일을 지운다. 이미 없으면 아무 일도 하지 않는다."""
        ...

    def delete_prefix(self, prefix: str) -> None:
        """`<owner>/` 또는 `<owner>/<session>/` 아래의 모든 파일을 지운다."""
        ...


def make_key(owner_id: str, session_id: str, asset_id: str) -> str:
    key = f"{owner_id}/{session_id}/{asset_id}"
    validate_key(key)
    return key


def _segments(value: str) -> list[str]:
    if not value or "\x00" in value or "\\" in value or value.startswith("/"):
        raise InvalidBlobKey("키 형식이 올바르지 않습니다")
    parts = value.split("/")
    for part in parts:
        if ".." in part or not _SEGMENT_RE.fullmatch(part):
            raise InvalidBlobKey("키 형식이 올바르지 않습니다")
    return parts


def validate_key(key: str) -> None:
    if len(_segments(key)) != KEY_SEGMENTS:
        raise InvalidBlobKey("키는 <owner>/<session>/<asset> 형식이어야 합니다")


def validate_prefix(prefix: str) -> str:
    """접두사를 `<owner>` 또는 `<owner>/<session>` 형태로 정리해 돌려준다."""
    parts = _segments(prefix.rstrip("/"))
    if len(parts) >= KEY_SEGMENTS:
        raise InvalidBlobKey("접두사는 <owner> 또는 <owner>/<session> 형식이어야 합니다")
    return "/".join(parts)


class LocalBlobStore:
    """`root` 아래에 파일로 저장한다. 임시 파일에 쓴 뒤 옮겨서 반쯤 쓴 파일을 남기지 않는다."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._root_resolved = self.root.resolve()

    def _path(self, key: str) -> Path:
        validate_key(key)
        return self._inside_root(self.root / key)

    def _inside_root(self, path: Path) -> Path:
        # 심볼릭 링크로 저장소 밖을 가리키는 경우까지 막는다.
        resolved = path.resolve()
        if not resolved.is_relative_to(self._root_resolved):
            raise InvalidBlobKey("키가 저장소 밖을 가리킵니다")
        return path

    def put(self, key: str, data: BinaryIO) -> int:
        path = self._path(key)
        tmp_name: str | None = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".tmp-", delete=False) as tmp:
                tmp_name = tmp.name
                shutil.copyfileobj(data, tmp, _COPY_CHUNK)
                size = tmp.tell()
            os.replace(tmp_name, path)
        except OSError as exc:
            if tmp_name:
                with contextlib.suppress(OSError):
                    os.unlink(tmp_name)
            if exc.errno in _FULL_ERRNOS:
                raise StorageFull(exc.errno, "저장 공간이 부족합니다") from exc
            raise
        return size

    def open(self, key: str) -> BinaryIO:
        path = self._path(key)
        try:
            return path.open("rb")
        except FileNotFoundError as exc:
            raise BlobNotFound(key) from exc

    def delete(self, key: str) -> None:
        path = self._path(key)
        with contextlib.suppress(FileNotFoundError):
            path.unlink()

    def delete_prefix(self, prefix: str) -> None:
        path = self._inside_root(self.root / validate_prefix(prefix))
        shutil.rmtree(path, ignore_errors=True)
