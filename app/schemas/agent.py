"""Pydantic schemas for agents."""

from __future__ import annotations

from datetime import datetime

from app.schemas.common import BaseSchema


class AgentRead(BaseSchema):
    id: str
    display_name: str
    role: str
    active: bool
    created_at: datetime

