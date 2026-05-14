"""Pydantic schemas for artifacts."""

from __future__ import annotations

from datetime import datetime

from app.schemas.common import BaseSchema, StrictSchema


class ArtifactCreate(StrictSchema):
    artifact_type: str
    content: str


class ArtifactRead(BaseSchema):
    id: int
    ticket_id: int
    artifact_type: str
    author: str
    content: str
    created_at: datetime
