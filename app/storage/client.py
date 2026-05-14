"""S3-compatible storage client."""

from __future__ import annotations

import functools
from typing import Any

import boto3
from botocore.client import Config

from app.config import get_settings


@functools.lru_cache
def get_storage_client() -> Any:
    """Return a cached boto3 S3 client configured from settings."""
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.storage_endpoint_url,
        aws_access_key_id=settings.storage_access_key,
        aws_secret_access_key=settings.storage_secret_key,
        region_name=settings.storage_region,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": settings.storage_addressing_style},
        ),
    )


def get_bucket_name() -> str:
    return get_settings().storage_bucket
