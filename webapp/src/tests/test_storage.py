"""`LocalBlobStore` 단위 테스트 (요구사항 8.4, 8.7, 8.8)."""

from __future__ import annotations

import errno
import io
from pathlib import Path

import pytest

from open_attendee.storage import (
    BlobNotFound,
    InvalidBlobKey,
    LocalBlobStore,
    StorageFull,
    make_key,
)

KEY = "owner/sess1/asset1"


@pytest.fixture
def store(tmp_path: Path) -> LocalBlobStore:
    return LocalBlobStore(tmp_path / "blobs")


def test_put_open_delete_roundtrip(store: LocalBlobStore) -> None:
    assert store.put(KEY, io.BytesIO(b"hello")) == 5
    with store.open(KEY) as f:
        assert f.read() == b"hello"
    store.delete(KEY)
    with pytest.raises(BlobNotFound):
        store.open(KEY)


def test_put_overwrites_and_leaves_no_temp_files(store: LocalBlobStore) -> None:
    store.put(KEY, io.BytesIO(b"one"))
    store.put(KEY, io.BytesIO(b"three"))
    with store.open(KEY) as f:
        assert f.read() == b"three"
    names = [p.name for p in (store.root / "owner" / "sess1").iterdir()]
    assert names == ["asset1"]


def test_delete_missing_key_is_a_noop(store: LocalBlobStore) -> None:
    store.delete(KEY)


def test_make_key_uses_owner_session_asset_format() -> None:
    assert make_key("owner", "s1", "a1") == "owner/s1/a1"


@pytest.mark.parametrize(
    "key",
    [
        "",
        "/etc/passwd",
        "../owner/s/a",
        "owner/../a",
        "owner/s/..",
        "owner/s/../../x",
        "owner/s/a/../b",
        "owner//a",
        "owner/s",
        "owner/s/a/b",
        "owner/s/.hidden",
        "owner\\s\\a",
        "owner/s/a\x00",
        "owner/s/a b",
        "owner/s/한글",
        "owner/s/a..b",
        "C:/x/y",
    ],
)
def test_invalid_keys_are_rejected_before_touching_the_disk(
    store: LocalBlobStore, key: str
) -> None:
    for call in (
        lambda: store.put(key, io.BytesIO(b"x")),
        lambda: store.open(key),
        lambda: store.delete(key),
    ):
        with pytest.raises(InvalidBlobKey):
            call()
    assert list(store.root.iterdir()) == []


def test_symlink_escape_is_rejected(store: LocalBlobStore, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (store.root / "owner").symlink_to(outside, target_is_directory=True)
    with pytest.raises(InvalidBlobKey):
        store.put(KEY, io.BytesIO(b"x"))
    assert list(outside.iterdir()) == []


def test_disk_full_raises_distinguishable_error_and_cleans_up(
    store: LocalBlobStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    def full(*_args: object, **_kwargs: object) -> None:
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr("open_attendee.storage.shutil.copyfileobj", full)
    with pytest.raises(StorageFull):
        store.put(KEY, io.BytesIO(b"data"))
    parent = store.root / "owner" / "sess1"
    assert not parent.exists() or list(parent.iterdir()) == []


def test_other_os_errors_are_not_reported_as_full(
    store: LocalBlobStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    def denied(*_args: object, **_kwargs: object) -> None:
        raise PermissionError(errno.EACCES, "denied")

    monkeypatch.setattr("open_attendee.storage.shutil.copyfileobj", denied)
    with pytest.raises(PermissionError):
        store.put(KEY, io.BytesIO(b"data"))


def test_delete_prefix_removes_only_that_session(store: LocalBlobStore) -> None:
    store.put("owner/s1/a", io.BytesIO(b"1"))
    store.put("owner/s1/a.thumb", io.BytesIO(b"1"))
    store.put("owner/s2/b", io.BytesIO(b"2"))
    store.delete_prefix("owner/s1")
    with pytest.raises(BlobNotFound):
        store.open("owner/s1/a")
    with pytest.raises(BlobNotFound):
        store.open("owner/s1/a.thumb")
    with store.open("owner/s2/b") as f:
        assert f.read() == b"2"


@pytest.mark.parametrize("prefix", ["", "..", "owner/..", "/owner", "owner/s/a"])
def test_delete_prefix_rejects_bad_prefixes(store: LocalBlobStore, prefix: str) -> None:
    store.put(KEY, io.BytesIO(b"x"))
    with pytest.raises(InvalidBlobKey):
        store.delete_prefix(prefix)
    with store.open(KEY) as f:
        assert f.read() == b"x"


def test_delete_prefix_on_missing_directory_is_a_noop(store: LocalBlobStore) -> None:
    store.delete_prefix("owner/nothing")
