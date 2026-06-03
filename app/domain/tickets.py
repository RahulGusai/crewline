"""Ticket domain operations: create, update, transition, assign, query."""

from __future__ import annotations

import re
from typing import Any

import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.actor import parse_actor
from app.domain.agents import get_agent
from app.domain.exceptions import (
    ActorNotPermittedError,
    InvalidPrUrlFormatError,
    PrUrlAlreadySetError,
    PrUrlRepoMismatchError,
    TicketNotFoundError,
)
from app.domain.mailbox import (
    send_ticket_assigned,
    send_ticket_cancelled,
    send_ticket_review_requested,
    send_ticket_unassigned,
)
from app.domain.state_machine import validate_transition
from app.enums import ActorKind, TicketStatus
from app.models.ticket import Ticket
from app.models.ticket_audit_log import TicketAuditLog

logger = structlog.get_logger(__name__)

PR_URL_RE = re.compile(r"^https://github\.com/([^/]+)/([^/]+)/pull/([0-9]+)$")
AUTO_QA_ACTOR = "system:system"


async def _get_ticket_for_update(session: AsyncSession, ticket_id: int) -> Ticket:
    """Fetch a ticket with FOR UPDATE row lock."""
    stmt = select(Ticket).where(Ticket.id == ticket_id).with_for_update()
    result = await session.execute(stmt)
    ticket = result.scalar_one_or_none()
    if ticket is None:
        raise TicketNotFoundError(ticket_id)
    return ticket


def _is_reason_provided(reason: str | None) -> bool:
    return reason is not None and reason.strip() != ""


async def create_ticket(
    session: AsyncSession,
    *,
    title: str,
    description: str | None,
    created_by: str,
    owner_agent_id: str | None = None,
    repo_full_name: str,
    related_repo_full_names: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> Ticket:
    """Create a new ticket in TODO status, optionally assigned to an agent."""
    creator = parse_actor(created_by)
    owner = await get_agent(session, owner_agent_id) if owner_agent_id is not None else None
    await validate_transition(
        session,
        ticket=None,
        to_status=TicketStatus.TODO,
        actor=creator,
        pm_override=False,
        reason=None,
    )

    ticket = Ticket(
        title=title,
        description=description,
        status=TicketStatus.TODO.value,
        owner_agent_id=owner.id if owner is not None else None,
        created_by=created_by,
        repo_full_name=repo_full_name,
        related_repo_full_names=related_repo_full_names or [],
        metadata_=metadata or {},
    )
    session.add(ticket)
    await session.flush()

    audit = TicketAuditLog(
        ticket_id=ticket.id,
        from_status=None,
        to_status=TicketStatus.TODO.value,
        from_owner=None,
        to_owner=owner.id if owner is not None else None,
        actor=created_by,
        reason=None,
        pm_override=False,
    )
    session.add(audit)
    await session.flush()

    if owner is not None:
        await send_ticket_assigned(
            session,
            ticket_id=ticket.id,
            title=title,
            recipient=f"agent:{owner.id}",
            sender=created_by,
        )

    logger.info(
        "ticket.created",
        ticket_id=ticket.id,
        owner_agent_id=owner.id if owner is not None else None,
        created_by=created_by,
    )
    return ticket


async def update_ticket(
    session: AsyncSession,
    *,
    ticket_id: int,
    actor: str,
    title: str | None = None,
    description: str | None = None,
    related_repo_full_names: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> Ticket:
    """Edit ticket fields. PM-only in v0."""
    parsed = parse_actor(actor)
    if parsed.kind != ActorKind.HUMAN:
        raise ActorNotPermittedError(actor=actor, action="update ticket fields")

    ticket = await _get_ticket_for_update(session, ticket_id)

    changed_fields: list[str] = []
    if title is not None and title != ticket.title:
        ticket.title = title
        changed_fields.append("title")
    if description is not None and description != ticket.description:
        ticket.description = description
        changed_fields.append("description")
    if related_repo_full_names is not None and related_repo_full_names != ticket.related_repo_full_names:
        ticket.related_repo_full_names = related_repo_full_names
        changed_fields.append("related_repo_full_names")
    if metadata is not None and metadata != ticket.metadata_:
        ticket.metadata_ = metadata
        changed_fields.append("metadata")

    await session.flush()

    logger.info(
        "ticket.updated",
        ticket_id=ticket_id,
        actor=actor,
        changed_fields=changed_fields,
    )
    return ticket


async def transition_ticket(
    session: AsyncSession,
    *,
    ticket_id: int,
    to_status: TicketStatus,
    actor: str,
    reason: str | None = None,
    pm_override: bool = False,
) -> Ticket:
    """Transition a ticket to a new status."""
    parsed = parse_actor(actor)

    ticket = await _get_ticket_for_update(session, ticket_id)
    from_status = TicketStatus(ticket.status)

    await validate_transition(
        session,
        ticket=ticket,
        to_status=to_status,
        actor=parsed,
        pm_override=pm_override,
        reason=reason,
    )

    ticket.status = to_status.value
    audit = TicketAuditLog(
        ticket_id=ticket.id,
        from_status=from_status.value,
        to_status=to_status.value,
        from_owner=None,
        to_owner=None,
        actor=actor,
        reason=reason if _is_reason_provided(reason) else None,
        pm_override=pm_override,
    )
    session.add(audit)
    await session.flush()

    if from_status == TicketStatus.IN_PROGRESS and to_status == TicketStatus.IN_QA:
        await send_ticket_review_requested(
            session,
            ticket_id=ticket.id,
            recipient="agent:sentinel",
            sender=AUTO_QA_ACTOR,
        )

    if to_status == TicketStatus.CANCELLED and ticket.owner_agent_id is not None:
        await send_ticket_cancelled(
            session,
            ticket_id=ticket.id,
            recipient=f"agent:{ticket.owner_agent_id}",
            sender=actor,
            reason=reason,
        )

    logger.info(
        "ticket.transitioned",
        ticket_id=ticket_id,
        from_status=from_status.value,
        to_status=to_status.value,
        actor=actor,
        pm_override=pm_override,
        reason_provided=_is_reason_provided(reason),
    )
    return ticket


def parse_github_pr_url(pr_url: str) -> tuple[str, str, int]:
    match = PR_URL_RE.match(pr_url)
    if match is None:
        raise InvalidPrUrlFormatError(pr_url)
    owner, repo, number = match.groups()
    return owner, repo, int(number)


async def set_ticket_pr_url(
    session: AsyncSession,
    *,
    ticket_id: int,
    actor: str,
    pr_url: str,
) -> Ticket:
    parsed = parse_actor(actor)
    if parsed.kind != ActorKind.AGENT:
        raise ActorNotPermittedError(actor=actor, action="set ticket PR URL")

    ticket = await _get_ticket_for_update(session, ticket_id)
    if ticket.owner_agent_id != parsed.id:
        raise ActorNotPermittedError(actor=actor, action=f"set PR URL for ticket {ticket_id}")
    if ticket.pr_url is not None:
        raise PrUrlAlreadySetError(ticket_id)

    owner, repo, _ = parse_github_pr_url(pr_url)
    pr_repo = f"{owner}/{repo}"
    if pr_repo != ticket.repo_full_name:
        raise PrUrlRepoMismatchError(pr_repo=pr_repo, ticket_repo=ticket.repo_full_name)

    ticket.pr_url = pr_url
    await session.flush()
    logger.info("ticket.pr_url_set", ticket_id=ticket_id, actor=actor, repo_full_name=pr_repo)
    return ticket


async def assign_ticket(
    session: AsyncSession,
    *,
    ticket_id: int,
    new_owner_agent_id: str,
    actor: str,
    reason: str | None = None,
) -> Ticket:
    """Reassign a ticket to a different agent. PM-only in v0."""
    parsed = parse_actor(actor)
    if parsed.kind != ActorKind.HUMAN:
        raise ActorNotPermittedError(actor=actor, action="assign ticket")

    new_owner = await get_agent(session, new_owner_agent_id)
    ticket = await _get_ticket_for_update(session, ticket_id)
    old_owner_id = ticket.owner_agent_id

    if old_owner_id == new_owner.id:
        logger.info(
            "ticket.assigned",
            ticket_id=ticket_id,
            from_owner=old_owner_id,
            to_owner=new_owner.id,
            actor=actor,
            no_op=True,
        )
        return ticket

    ticket.owner_agent_id = new_owner.id
    audit = TicketAuditLog(
        ticket_id=ticket.id,
        from_status=None,
        to_status=None,
        from_owner=old_owner_id,
        to_owner=new_owner.id,
        actor=actor,
        reason=reason if _is_reason_provided(reason) else None,
        pm_override=False,
    )
    session.add(audit)
    await session.flush()

    if old_owner_id is not None:
        await send_ticket_unassigned(
            session,
            ticket_id=ticket.id,
            recipient=f"agent:{old_owner_id}",
            sender=actor,
        )
    await send_ticket_assigned(
        session,
        ticket_id=ticket.id,
        title=ticket.title,
        recipient=f"agent:{new_owner.id}",
        sender=actor,
    )

    logger.info(
        "ticket.assigned",
        ticket_id=ticket_id,
        from_owner=old_owner_id,
        to_owner=new_owner.id,
        actor=actor,
    )
    return ticket


async def get_ticket(session: AsyncSession, ticket_id: int) -> Ticket:
    """Fetch a single ticket by id."""
    result = await session.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = result.scalar_one_or_none()
    if ticket is None:
        raise TicketNotFoundError(ticket_id)
    return ticket


async def list_tickets(
    session: AsyncSession,
    *,
    status: TicketStatus | None = None,
    owner_agent_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Ticket]:
    """List tickets with optional filters. Newest first."""
    if limit < 1 or limit > 200:
        limit = 50
    if offset < 0:
        offset = 0

    conditions = []
    if status is not None:
        conditions.append(Ticket.status == status.value)
    if owner_agent_id is not None:
        conditions.append(Ticket.owner_agent_id == owner_agent_id)

    stmt = select(Ticket)
    if conditions:
        stmt = stmt.where(and_(*conditions))
    stmt = stmt.order_by(Ticket.created_at.desc()).limit(limit).offset(offset)

    result = await session.execute(stmt)
    return list(result.scalars().all())
