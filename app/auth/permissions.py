"""Authorization helpers for authenticated actors."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.actor import Actor
from app.domain.agents import get_agent
from app.domain.exceptions import ActorNotPermittedError
from app.enums import ActorKind, AgentRole
from app.models.ticket import Ticket


def require_pm(actor: Actor, action: str) -> None:
    """Raise if actor is not the PM."""
    if actor.kind != ActorKind.HUMAN:
        raise ActorNotPermittedError(actor=actor.raw, action=action)


def require_owned_ticket(actor: Actor, ticket: Ticket, action: str) -> None:
    """Agents may only operate on tickets they own."""
    if actor.kind == ActorKind.AGENT and ticket.owner_agent_id != actor.id:
        raise ActorNotPermittedError(actor=actor.raw, action=action)


async def require_ticket_read_access(
    session: AsyncSession,
    actor: Actor,
    ticket: Ticket,
    action: str,
) -> None:
    """Allow PMs and all agents to read ticket context."""
    return


async def require_owned_or_qa_agent_ticket_access(
    session: AsyncSession,
    actor: Actor,
    ticket: Ticket,
    action: str,
) -> None:
    """Allow ticket owners and QA-role agents for agent-authenticated ticket writes."""
    if actor.kind != ActorKind.AGENT:
        return
    if ticket.owner_agent_id == actor.id:
        return

    agent = await get_agent(session, actor.id)
    if agent.role == AgentRole.QA.value:
        return

    raise ActorNotPermittedError(actor=actor.raw, action=action)


async def require_agent_ticket_read_access(
    session: AsyncSession,
    actor: Actor,
    ticket: Ticket,
    action: str,
) -> None:
    """Allow any agent to read ticket context, but reject human actors."""
    if actor.kind != ActorKind.AGENT:
        raise ActorNotPermittedError(actor=actor.raw, action=action)
    await require_ticket_read_access(session, actor, ticket, action)
