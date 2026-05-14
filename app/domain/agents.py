"""Agent registry queries."""

from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import AgentNotFoundError
from app.enums import AgentRole
from app.models.agent import Agent

logger = structlog.get_logger(__name__)


async def get_agent(session: AsyncSession, agent_id: str) -> Agent:
    """Fetch one agent by id."""
    result = await session.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if agent is None:
        raise AgentNotFoundError(agent_id)
    return agent


async def list_agents(
    session: AsyncSession,
    *,
    role: AgentRole | None = None,
) -> list[Agent]:
    """List all agents, optionally filtered by role."""
    stmt = select(Agent)
    if role is not None:
        stmt = stmt.where(Agent.role == role.value)
    stmt = stmt.order_by(Agent.role, Agent.id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def pick_next_owner(session: AsyncSession, role: AgentRole) -> Agent:
    """Return the active agent for a given role."""
    stmt = (
        select(Agent)
        .where(Agent.role == role.value, Agent.active.is_(True))
        .order_by(Agent.id)
        .limit(1)
    )
    result = await session.execute(stmt)
    agent = result.scalar_one_or_none()
    if agent is None:
        logger.error("agent.lookup_failed", role=role.value)
        raise AgentNotFoundError(f"<no active agent for role={role.value}>")
    return agent

