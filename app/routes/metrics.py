"""HTTP route for computed ticket metrics."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_actor
from app.auth.permissions import require_owned_ticket
from app.db import get_session
from app.domain.actor import Actor
from app.domain.metrics import compute_ticket_metrics
from app.domain.tickets import get_ticket
from app.enums import ActorKind
from app.schemas.ticket import TicketMetricsRead

router = APIRouter(prefix="/tickets", tags=["metrics"])


@router.get("/{ticket_id}/metrics", response_model=TicketMetricsRead)
async def get_metrics_route(
    ticket_id: int,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TicketMetricsRead:
    if actor.kind == ActorKind.AGENT:
        ticket = await get_ticket(session, ticket_id)
        require_owned_ticket(actor, ticket, f"read metrics for ticket {ticket_id}")

    metrics = await compute_ticket_metrics(session, ticket_id)
    return TicketMetricsRead.model_validate(metrics)
