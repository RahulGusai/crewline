"""Schemas for runtime activity logs and costs."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from app.schemas.common import BaseSchema, StrictSchema

RuntimeType = Literal["ticket_work", "question_handling", "review"]
RuntimeOutcome = Literal["completed", "max_turns_hit", "failed"]
AgentId = Literal["cortex", "lumen", "architect", "sentinel"]


class RuntimeLogCreate(StrictSchema):
    ticket_id: int
    agent_id: AgentId
    runtime_type: RuntimeType
    started_at: datetime
    ended_at: datetime | None = None
    outcome: RuntimeOutcome
    total_turns: int | None = None
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    classification: str | None = None
    content: str


class RuntimeLogCreated(BaseSchema):
    id: int
    created_at: datetime


class RuntimeLogSummary(BaseSchema):
    id: int
    ticket_id: int
    agent_id: str
    runtime_type: str
    started_at: datetime
    ended_at: datetime | None
    outcome: str
    total_turns: int | None
    model: str | None
    input_tokens: int | None
    output_tokens: int | None
    classification: str | None
    created_at: datetime
    cost_usd: float | None


class RuntimeLogDetail(RuntimeLogSummary):
    content: str


class TicketCostBreakdown(BaseSchema):
    runtime_log_id: int
    agent_id: str
    runtime_type: str
    cost_usd: float | None


class TicketCostRead(BaseSchema):
    ticket_id: int
    total_cost_usd: float
    runtime_count: int
    breakdown: list[TicketCostBreakdown]
