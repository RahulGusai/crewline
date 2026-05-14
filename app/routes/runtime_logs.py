"""HTTP routes for runtime activity logs and cost summaries."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_actor
from app.auth.permissions import require_owned_ticket
from app.db import get_session
from app.domain.actor import Actor
from app.domain.exceptions import (
    ActorNotPermittedError,
    RuntimeLogTicketMismatchError,
)
from app.domain.runtime_logs import create_runtime_log, get_runtime_log, list_runtime_logs
from app.domain.tickets import get_ticket
from app.enums import ActorKind
from app.models.runtime_log import RuntimeLog
from app.models.ticket import Ticket
from app.pricing import compute_cost
from app.schemas.runtime_log import (
    RuntimeLogCreate,
    RuntimeLogCreated,
    RuntimeLogDetail,
    RuntimeLogSummary,
    TicketCostBreakdown,
    TicketCostRead,
)

ticket_router = APIRouter(prefix="/tickets", tags=["runtime-logs"])
router = APIRouter(prefix="/runtime-logs", tags=["runtime-logs"])


def _serialize_summary(log: RuntimeLog) -> RuntimeLogSummary:
    return RuntimeLogSummary(
        id=log.id,
        ticket_id=log.ticket_id,
        agent_id=log.agent_id,
        runtime_type=log.runtime_type,
        started_at=log.started_at,
        ended_at=log.ended_at,
        outcome=log.outcome,
        total_turns=log.total_turns,
        model=log.model,
        input_tokens=log.input_tokens,
        output_tokens=log.output_tokens,
        classification=log.classification,
        created_at=log.created_at,
        cost_usd=compute_cost(log.model, log.input_tokens, log.output_tokens),
    )


def _serialize_detail(log: RuntimeLog) -> RuntimeLogDetail:
    summary = _serialize_summary(log)
    return RuntimeLogDetail(**summary.model_dump(), content=log.content)


def _check_read_access(actor: Actor, ticket: Ticket) -> None:
    if actor.kind == ActorKind.AGENT:
        require_owned_ticket(actor, ticket, f"read runtime logs for ticket {ticket.id}")


@ticket_router.post(
    "/{ticket_id}/runtime-logs",
    status_code=status.HTTP_201_CREATED,
    response_model=RuntimeLogCreated,
)
async def create_runtime_log_route(
    ticket_id: int,
    payload: RuntimeLogCreate,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RuntimeLogCreated:
    if payload.ticket_id != ticket_id:
        raise RuntimeLogTicketMismatchError(ticket_id, payload.ticket_id)
    if actor.kind != ActorKind.AGENT or actor.id != payload.agent_id:
        raise ActorNotPermittedError(actor=actor.raw, action="create runtime log")
    await get_ticket(session, ticket_id)
    log = await create_runtime_log(
        session,
        ticket_id=ticket_id,
        agent_id=payload.agent_id,
        runtime_type=payload.runtime_type,
        started_at=payload.started_at,
        ended_at=payload.ended_at,
        outcome=payload.outcome,
        total_turns=payload.total_turns,
        model=payload.model,
        input_tokens=payload.input_tokens,
        output_tokens=payload.output_tokens,
        classification=payload.classification,
        content=payload.content,
    )
    return RuntimeLogCreated(id=log.id, created_at=log.created_at)


@ticket_router.get(
    "/{ticket_id}/runtime-logs",
    response_model=list[RuntimeLogSummary],
)
async def list_runtime_logs_route(
    ticket_id: int,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
    agent_id: Annotated[str | None, Query()] = None,
) -> list[RuntimeLogSummary]:
    ticket = await get_ticket(session, ticket_id)
    _check_read_access(actor, ticket)
    logs = await list_runtime_logs(session, ticket_id=ticket_id, agent_id=agent_id)
    return [_serialize_summary(log) for log in logs]


@ticket_router.get("/{ticket_id}/cost", response_model=TicketCostRead)
async def get_ticket_cost_route(
    ticket_id: int,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TicketCostRead:
    ticket = await get_ticket(session, ticket_id)
    _check_read_access(actor, ticket)
    logs = await list_runtime_logs(session, ticket_id=ticket_id)
    breakdown = [
        TicketCostBreakdown(
            runtime_log_id=log.id,
            agent_id=log.agent_id,
            runtime_type=log.runtime_type,
            cost_usd=compute_cost(log.model, log.input_tokens, log.output_tokens),
        )
        for log in logs
    ]
    return TicketCostRead(
        ticket_id=ticket_id,
        total_cost_usd=sum(item.cost_usd for item in breakdown if item.cost_usd is not None),
        runtime_count=len(logs),
        breakdown=breakdown,
    )


@router.get("/{log_id}", response_model=RuntimeLogDetail)
async def get_runtime_log_route(
    log_id: int,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RuntimeLogDetail:
    log = await get_runtime_log(session, log_id)
    ticket = await get_ticket(session, log.ticket_id)
    _check_read_access(actor, ticket)
    return _serialize_detail(log)
