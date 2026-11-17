from io import BytesIO

import pytest
from botocore.response import StreamingBody
from botocore.stub import ANY, Stubber

from open_attendee.s3_storage import S3BlobStore
from open_attendee.storage import BlobNotFound, StorageUnavailable

BUCKET = "open-attendee-test"
PREFIX = "owner/session"
KEY = f"{PREFIX}/asset"


@pytest.fixture
def store(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    blob = S3BlobStore(BUCKET, region="us-east-1", endpoint="http://127.0.0.1:9000")
    try:
        yield blob
    finally:
        blob.close()


class NonSeekable(BytesIO):
    def seekable(self) -> bool:
        return False


def test_put_uses_remaining_bytes_and_accepts_nonseekable_streams(store):
    data = BytesIO(b"prefix payload")
    data.seek(len(b"prefix "))
    with Stubber(store.client) as stub:
        stub.add_response(
            "put_object", {}, {"Bucket": BUCKET, "Key": KEY, "Body": data, "ContentLength": 7}
        )
        stub.add_response(
            "put_object", {}, {"Bucket": BUCKET, "Key": KEY, "Body": ANY, "ContentLength": 7}
        )
        assert store.put(KEY, data) == 7
        assert data.tell() == len(b"prefix ")
        assert store.put(KEY, NonSeekable(b"payload")) == 7
        stub.assert_no_pending_responses()


def test_open_distinguishes_missing_object_from_denied_access(store):
    params = {"Bucket": BUCKET, "Key": KEY}
    with Stubber(store.client) as stub:
        body = StreamingBody(BytesIO(b"attachment"), len(b"attachment"))
        stub.add_response("get_object", {"Body": body}, params)
        stub.add_client_error(
            "get_object",
            service_error_code="NoSuchKey",
            http_status_code=404,
            expected_params=params,
        )
        stub.add_client_error(
            "get_object",
            service_error_code="AccessDenied",
            http_status_code=403,
            expected_params=params,
        )
        with store.open(KEY) as stream:
            assert stream.read() == b"attachment"
        with pytest.raises(BlobNotFound):
            store.open(KEY)
        with pytest.raises(StorageUnavailable):
            store.open(KEY)
        stub.assert_no_pending_responses()


def test_delete_prefix_limits_scope_and_follows_continuation_token(store):
    params = {"Bucket": BUCKET, "Prefix": f"{PREFIX}/"}
    thumb = f"{KEY}.thumb.jpg"
    with Stubber(store.client) as stub:
        stub.add_response(
            "list_objects_v2",
            {"Contents": [{"Key": KEY}], "IsTruncated": True, "NextContinuationToken": "next"},
            params,
        )
        stub.add_response(
            "delete_objects",
            {},
            {"Bucket": BUCKET, "Delete": {"Objects": [{"Key": KEY}], "Quiet": True}},
        )
        stub.add_response(
            "list_objects_v2",
            {"Contents": [{"Key": thumb}], "IsTruncated": False},
            {**params, "ContinuationToken": "next"},
        )
        stub.add_response(
            "delete_objects",
            {},
            {"Bucket": BUCKET, "Delete": {"Objects": [{"Key": thumb}], "Quiet": True}},
        )
        store.delete_prefix(PREFIX)
        stub.assert_no_pending_responses()


def test_delete_prefix_surfaces_partial_failures(store):
    with Stubber(store.client) as stub:
        stub.add_response(
            "list_objects_v2",
            {"Contents": [{"Key": KEY}], "IsTruncated": False},
            {"Bucket": BUCKET, "Prefix": f"{PREFIX}/"},
        )
        stub.add_response(
            "delete_objects",
            {"Errors": [{"Key": KEY, "Code": "AccessDenied"}]},
            {"Bucket": BUCKET, "Delete": {"Objects": [{"Key": KEY}], "Quiet": True}},
        )
        with pytest.raises(StorageUnavailable):
            store.delete_prefix(PREFIX)
        stub.assert_no_pending_responses()
