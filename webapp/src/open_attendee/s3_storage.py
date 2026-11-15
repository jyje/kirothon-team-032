"""S3 첨부 저장소. 객체는 기존 소유자/행사/자료 키로 저장한다."""

from __future__ import annotations

import os
import shutil
from tempfile import SpooledTemporaryFile
from typing import BinaryIO, cast

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from open_attendee.storage import (
    BlobNotFound,
    StorageUnavailable,
    validate_key,
    validate_prefix,
)

_S3_ERRORS = (ClientError, BotoCoreError)


class S3BlobStore:
    def __init__(
        self, bucket: str, *, region: str | None = None, endpoint: str | None = None
    ) -> None:
        self.bucket = bucket
        self.client = boto3.client(
            "s3",
            region_name=region,
            endpoint_url=endpoint,
            config=Config(s3={"addressing_style": "path"}) if endpoint else None,
        )

    def close(self) -> None:
        self.client.close()

    def put(self, key: str, data: BinaryIO) -> int:
        validate_key(key)
        if data.seekable():
            return self._put(key, data)
        with SpooledTemporaryFile(max_size=8 * 1024 * 1024) as spool:
            shutil.copyfileobj(data, spool)
            spool.seek(0)
            return self._put(key, cast(BinaryIO, spool))

    def _put(self, key: str, data: BinaryIO) -> int:
        start = data.tell()
        data.seek(0, os.SEEK_END)
        size = data.tell() - start
        data.seek(start)
        try:
            self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentLength=size)
        except _S3_ERRORS as exc:
            raise StorageUnavailable("첨부 파일을 저장하지 못했어요.") from exc
        return size

    def open(self, key: str) -> BinaryIO:
        validate_key(key)
        try:
            return cast(BinaryIO, self.client.get_object(Bucket=self.bucket, Key=key)["Body"])
        except ClientError as exc:
            if exc.response["Error"]["Code"] in {"NoSuchKey", "NotFound", "404"}:
                raise BlobNotFound(key) from exc
            raise StorageUnavailable("첨부 파일을 읽지 못했어요.") from exc
        except BotoCoreError as exc:
            raise StorageUnavailable("첨부 파일을 읽지 못했어요.") from exc

    def delete(self, key: str) -> None:
        validate_key(key)
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except _S3_ERRORS as exc:
            raise StorageUnavailable("첨부 파일을 지우지 못했어요.") from exc

    def delete_prefix(self, prefix: str) -> None:
        boundary = validate_prefix(prefix) + "/"
        try:
            pages = self.client.get_paginator("list_objects_v2").paginate(
                Bucket=self.bucket, Prefix=boundary
            )
            for page in pages:
                objects = [{"Key": item["Key"]} for item in page.get("Contents", [])]
                if not objects:
                    continue
                result = self.client.delete_objects(
                    Bucket=self.bucket, Delete={"Objects": objects, "Quiet": True}
                )
                if result.get("Errors"):
                    raise StorageUnavailable("일부 첨부 파일을 지우지 못했어요.")
        except _S3_ERRORS as exc:
            raise StorageUnavailable("행사의 첨부 파일을 지우지 못했어요.") from exc
