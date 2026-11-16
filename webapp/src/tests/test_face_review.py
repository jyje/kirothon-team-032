from __future__ import annotations

from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageChops
from sqlalchemy import Engine
from sqlmodel import Session, select

from open_attendee import jobs
from open_attendee.assets import THUMB_SUFFIX, AssetService
from open_attendee.config import Settings
from open_attendee.models import Asset, AssetKind, Job, JobKind, JobStatus
from open_attendee.processors.face_detection import PhotoRegion
from open_attendee.sessions import SessionService
from open_attendee.storage import BlobNotFound, LocalBlobStore, StorageUnavailable
from open_attendee.transcript_jobs import TranscriptionRunner

REGION = {"left": 0.25, "top": 0.25, "right": 0.75, "bottom": 0.75}


def photo_fixture() -> bytes:
    image = Image.new("RGB", (64, 64), "blue")
    for x in range(16, 48):
        for y in range(16, 48):
            image.putpixel((x, y), (255, 255, 255) if (x + y) % 2 else (0, 0, 0))
    result = BytesIO()
    image.save(result, format="PNG")
    return result.getvalue()


def test_owner_reviews_existing_photo_and_replaces_both_images(auth_client, db, blobs):
    event = auth_client.post("/api/sessions", json={"title": "행사"}).json()["id"]
    png = photo_fixture()
    upload = auth_client.post(
        f"/api/sessions/{event}/assets",
        data={"kind": "photo"},
        files={"file": ("pattern.png", png, "image/png")},
    )
    asset_id = upload.json()["id"]
    path = f"/api/sessions/{event}/assets/{asset_id}"
    original = auth_client.get(path + "/file").content
    thumbnail = auth_client.get(path + "/thumbnail").content
    before = db.get(Asset, asset_id).blob_key
    review = auth_client.get(path + "/face-review").json()
    assert review["detection_available"] and review["regions"] == []
    confirmed = auth_client.put(
        path + "/face-review",
        json={
            "revision": review["revision"],
            "regions": [],
        },
    )
    assert confirmed.json()["face_check_confirmed"]
    assert not confirmed.json()["faces_blurred"]
    assert auth_client.get(path + "/file").content == original

    changed = auth_client.put(
        path + "/face-review",
        json={
            "revision": review["revision"],
            "regions": [REGION],
        },
    )
    assert changed.status_code == 200 and changed.json()["faces_blurred"]
    after = auth_client.get(path + "/file")
    assert after.headers["cache-control"] == "private, no-store"
    image = Image.open(BytesIO(after.content))
    assert image.size == (64, 64)
    assert image.getpixel((4, 4)) == (0, 0, 255)
    assert 60 < image.getpixel((32, 32))[0] < 195
    assert ImageChops.difference(
        Image.open(BytesIO(thumbnail)),
        Image.open(BytesIO(auth_client.get(path + "/thumbnail").content)),
    ).getbbox()
    assert (
        auth_client.put(
            path + "/face-review",
            json={
                "revision": review["revision"],
                "regions": [REGION],
            },
        ).status_code
        == 409
    )

    # Wait on a durable cleanup that runs independently of the foreground request.
    job = db.exec(select(Job).where(Job.kind == JobKind.DELETE_PHOTO_VERSION)).one()
    assert job.payload["key"] == before
    if job.status is not JobStatus.DONE:
        from time import monotonic, sleep

        until = monotonic() + 5
        while job.status is not JobStatus.DONE and monotonic() < until:
            sleep(0.05)
            db.refresh(job)
    assert job.status is JobStatus.DONE
    for key in (before, before + THUMB_SUFFIX):
        with pytest.raises(BlobNotFound):
            blobs.open(key)


def test_other_owner_cannot_read_or_save_photo_review(
    auth_client: TestClient,
    db: Session,
    sessions: SessionService,
    blobs: LocalBlobStore,
    settings: Settings,
):
    event = sessions.create("other", "다른 행사")
    asset = AssetService(db, blobs, settings).store_upload(
        "other",
        event.id,
        AssetKind.PHOTO,
        "pattern.png",
        BytesIO(photo_fixture()),
    )
    path = f"/api/sessions/{event.id}/assets/{asset.id}/face-review"
    assert auth_client.get(path).status_code == 404
    assert (
        auth_client.put(path, json={"revision": "0" * 64, "regions": [REGION]}).status_code == 404
    )


def test_thumbnail_write_failure_leaves_previous_photo_pair(
    engine: Engine,
    db: Session,
    sessions: SessionService,
    blobs: LocalBlobStore,
    settings: Settings,
):
    class BrokenThumbnail(LocalBlobStore):
        def put(self, key, data):
            written = super().put(key, data)
            if key.endswith(THUMB_SUFFIX):
                raise StorageUnavailable("missing reply")
            return written

    event = sessions.create("owner", "행사")
    normal = AssetService(db, blobs, settings)
    asset = normal.store_upload(
        "owner",
        event.id,
        AssetKind.PHOTO,
        "pattern.png",
        BytesIO(photo_fixture()),
    )
    prior = set(blobs.root.rglob("*"))
    revision = normal.review_photo("owner", event.id, asset.id)["revision"]
    broken = AssetService(db, BrokenThumbnail(blobs.root), settings)
    with pytest.raises(StorageUnavailable):
        broken.save_photo_review("owner", event.id, asset.id, revision, [PhotoRegion(**REGION)])
    assert set(blobs.root.rglob("*")) == prior
    assert not db.get(Asset, asset.id).face_check_confirmed
    assert jobs.claim_next(engine, (JobKind.DELETE_PHOTO_VERSION,)) is None

    normal.save_photo_review("owner", event.id, asset.id, revision, [PhotoRegion(**REGION)])
    job = jobs.claim_next(engine, (JobKind.DELETE_PHOTO_VERSION,))
    assert job is not None
    jobs.process_job(engine, job, lambda: None, TranscriptionRunner(blobs, None))
    assert db.get(Job, job.id).status is JobStatus.DONE
