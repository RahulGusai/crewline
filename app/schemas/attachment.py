"""Pydantic schemas for ticket attachments."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.enums import AttachmentStatus
from app.schemas.common import BaseSchema, StrictSchema


class AttachmentUploadRequest(StrictSchema):
    filename: str = Field(..., min_length=1, max_length=500)
    content_type: str = Field(..., min_length=1, max_length=200)
    size_bytes: int = Field(..., ge=1)


class AttachmentUploadResponse(BaseSchema):
    attachment_id: int
    upload_url: str
    expires_in_seconds: int


class AttachmentRead(BaseSchema):
    id: int
    ticket_id: int
    filename: str
    content_type: str
    size_bytes: int
    uploaded_by: str
    status: AttachmentStatus
    created_at: datetime
    finalized_at: datetime | None


class AttachmentDownloadResponse(BaseSchema):
    download_url: str
    expires_in_seconds: int
    filename: str
