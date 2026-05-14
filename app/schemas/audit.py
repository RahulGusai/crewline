"""Pydantic schemas for the audit log."""

from __future__ import annotations

from datetime import datetime

from app.schemas.common import BaseSchema


class AuditEntryRead(BaseSchema):
    id: int
    ticket_id: int
    from_status: str | None
    to_status: str | None
    from_owner: str | None
    to_owner: str | None
    actor: str
    reason: str | None
    pm_override: bool
    trace_id: str | None
    occurred_at: datetime

