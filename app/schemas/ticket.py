"""Pydantic schemas for ticket inputs and outputs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from app.enums import TicketStatus
from app.schemas.common import BaseSchema, StrictSchema


class TicketCreate(StrictSchema):
    title: str
    description: str | None = None
    repo_full_name: str
    related_repo_full_names: list[str] = Field(default_factory=list)
    qa_notes: str | None = None
    owner_agent_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TicketUpdate(StrictSchema):
    title: str | None = None
    description: str | None = None
    related_repo_full_names: list[str] | None = None
    qa_notes: str | None = None
    metadata: dict[str, Any] | None = None


class TicketPrUrlUpdate(StrictSchema):
    pr_url: str


class TicketTransition(StrictSchema):
    to_status: TicketStatus
    reason: str | None = None
    pm_override: bool = False


class TicketAssign(StrictSchema):
    new_owner_agent_id: str
    reason: str | None = None


class TicketRead(BaseSchema):
    id: int
    title: str
    description: str | None
    status: TicketStatus
    owner_agent_id: str | None
    repo_full_name: str
    related_repo_full_names: list[str]
    qa_notes: str | None
    pr_url: str | None
    created_by: str
    created_at: datetime
    updated_at: datetime
    metadata_: dict[str, Any] = Field(serialization_alias="metadata")


class TicketMetricsRead(BaseSchema):
    ticket_id: int
    started_at: datetime | None
    completed_at: datetime | None
    total_elapsed_seconds: int | None
    blocked_seconds: int
    blocked_episodes: int
