"""High-level storage operations."""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterator
from typing import Any, cast

import structlog
from botocore.exceptions import BotoCoreError, ClientError

from app.config import get_settings
from app.storage.client import get_bucket_name, get_storage_client

logger = structlog.get_logger(__name__)


def generate_s3_key(ticket_id: int, filename: str) -> str:
    safe_filename = _sanitize_filename(filename)
    return f"tickets/{ticket_id}/{uuid.uuid4()}/{safe_filename}"


def _sanitize_filename(filename: str) -> str:
    basename = filename.replace("\\", "/").rsplit("/", 1)[-1]
    return re.sub(r"[^\w.\-]", "_", basename)[:200]


def generate_presigned_put_url(
    s3_key: str,
    content_type: str,
    content_length: int,
) -> str:
    settings = get_settings()
    client = get_storage_client()
    return cast(
        str,
        client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": get_bucket_name(),
                "Key": s3_key,
                "ContentType": content_type,
                "ContentLength": content_length,
            },
            ExpiresIn=settings.attachment_upload_url_ttl_seconds,
            HttpMethod="PUT",
        ),
    )


def generate_presigned_get_url(
    s3_key: str,
    download_filename: str,
) -> str:
    settings = get_settings()
    client = get_storage_client()
    return cast(
        str,
        client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": get_bucket_name(),
                "Key": s3_key,
                "ResponseContentDisposition": f'attachment; filename="{download_filename}"',
            },
            ExpiresIn=settings.attachment_download_url_ttl_seconds,
            HttpMethod="GET",
        ),
    )


def get_object_size(s3_key: str) -> int | None:
    client = get_storage_client()
    try:
        response = cast(dict[str, Any], client.head_object(Bucket=get_bucket_name(), Key=s3_key))
        return int(response["ContentLength"])
    except (BotoCoreError, ClientError):
        return None


def get_object_stream(s3_key: str) -> tuple[Iterator[bytes], int | None]:
    client = get_storage_client()
    response = cast(dict[str, Any], client.get_object(Bucket=get_bucket_name(), Key=s3_key))
    body = response["Body"]
    content_length = response.get("ContentLength")

    def chunks() -> Iterator[bytes]:
        try:
            yield from body.iter_chunks(chunk_size=1024 * 1024)
        finally:
            body.close()

    return chunks(), int(content_length) if content_length is not None else None


def verify_object_exists(s3_key: str) -> bool:
    return get_object_size(s3_key) is not None


def delete_object(s3_key: str) -> None:
    client = get_storage_client()
    client.delete_object(Bucket=get_bucket_name(), Key=s3_key)
    logger.info("storage.object.deleted", s3_key=s3_key)
