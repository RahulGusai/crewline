"""HTTP routes for ticket CRUD and transitions."""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_actor, require_pm_actor
from app.api.pagination import to_paginated
from app.auth.permissions import require_ticket_read_access
from app.db import get_session
from app.domain.actor import Actor
from app.domain.github import (
    pm_uuid_from_actor_id,
    require_active_installation,
    validate_ticket_repos,
)
from app.domain.tickets import (
    assign_ticket,
    create_ticket,
    get_ticket,
    list_tickets,
    transition_ticket,
    update_ticket,
)
from app.enums import ActorKind, TicketStatus
from app.schemas.pagination import Paginated
from app.schemas.ticket import (
    TicketAssign,
    TicketCreate,
    TicketRead,
    TicketTransition,
    TicketUpdate,
)

router = APIRouter(prefix="/tickets", tags=["tickets"])
logger = structlog.get_logger(__name__)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=TicketRead)
async def create_ticket_route(
    payload: TicketCreate,
    actor: Annotated[Actor, Depends(require_pm_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TicketRead:
    logger.debug(
        "tickets.create.payload",
        actor=actor.raw,
        payload=payload.model_dump(mode="json"),
    )
    installation = await require_active_installation(session, pm_uuid_from_actor_id(actor.id))
    await validate_ticket_repos(
        session,
        installation_id=installation.installation_id,
        repo_full_name=payload.repo_full_name,
        related_repo_full_names=payload.related_repo_full_names,
    )
    ticket = await create_ticket(
        session=session,
        title=payload.title,
        description=payload.description,
        created_by=actor.raw,
        owner_agent_id=payload.owner_agent_id,
        ticket_kind=payload.ticket_kind,
        repo_full_name=payload.repo_full_name,
        related_repo_full_names=payload.related_repo_full_names,
        metadata=payload.metadata,
    )
    return TicketRead.model_validate(ticket)


@router.get("", response_model=Paginated[TicketRead])
async def list_tickets_route(
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
    status_filter: Annotated[TicketStatus | None, Query(alias="status")] = None,
    owner_agent_id: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Paginated[TicketRead]:
    if actor.kind == ActorKind.AGENT:
        owner_agent_id = actor.id

    tickets = await list_tickets(
        session=session,
        status=status_filter,
        owner_agent_id=owner_agent_id,
        limit=limit,
        offset=offset,
    )
    items = [TicketRead.model_validate(ticket) for ticket in tickets]
    return to_paginated(items, limit=limit, offset=offset)


@router.get("/{ticket_id}", response_model=TicketRead)
async def get_ticket_route(
    ticket_id: int,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TicketRead:
    ticket = await get_ticket(session, ticket_id)
    await require_ticket_read_access(session, actor, ticket, f"read ticket {ticket_id}")
    return TicketRead.model_validate(ticket)


@router.patch("/{ticket_id}", response_model=TicketRead)
async def update_ticket_route(
    ticket_id: int,
    payload: TicketUpdate,
    actor: Annotated[Actor, Depends(require_pm_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TicketRead:
    if payload.related_repo_full_names is not None:
        existing = await get_ticket(session, ticket_id)
        installation = await require_active_installation(session, pm_uuid_from_actor_id(actor.id))
        await validate_ticket_repos(
            session,
            installation_id=installation.installation_id,
            repo_full_name=existing.repo_full_name,
            related_repo_full_names=payload.related_repo_full_names,
        )
    ticket = await update_ticket(
        session=session,
        ticket_id=ticket_id,
        actor=actor.raw,
        title=payload.title,
        description=payload.description,
        related_repo_full_names=payload.related_repo_full_names,
        metadata=payload.metadata,
    )
    await session.refresh(ticket)
    return TicketRead.model_validate(ticket)


@router.post(
    "/{ticket_id}/transitions",
    status_code=status.HTTP_200_OK,
    response_model=TicketRead,
)
async def transition_ticket_route(
    ticket_id: int,
    payload: TicketTransition,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TicketRead:
    ticket = await transition_ticket(
        session=session,
        ticket_id=ticket_id,
        to_status=payload.to_status,
        actor=actor.raw,
        reason=payload.reason,
        pm_override=payload.pm_override,
    )
    await session.refresh(ticket)
    return TicketRead.model_validate(ticket)


@router.post(
    "/{ticket_id}/assign",
    status_code=status.HTTP_200_OK,
    response_model=TicketRead,
)
async def assign_ticket_route(
    ticket_id: int,
    payload: TicketAssign,
    actor: Annotated[Actor, Depends(require_pm_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TicketRead:
    ticket = await assign_ticket(
        session=session,
        ticket_id=ticket_id,
        new_owner_agent_id=payload.new_owner_agent_id,
        actor=actor.raw,
        reason=payload.reason,
    )
    await session.refresh(ticket)
    return TicketRead.model_validate(ticket)
