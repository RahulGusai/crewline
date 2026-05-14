"""HTTP routes for the agent registry."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.domain.agents import get_agent, list_agents, pick_next_owner
from app.enums import AgentRole
from app.schemas.agent import AgentRead

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("", response_model=list[AgentRead])
async def list_agents_route(
    session: Annotated[AsyncSession, Depends(get_session)],
    role: Annotated[AgentRole | None, Query()] = None,
) -> list[AgentRead]:
    agents = await list_agents(session, role=role)
    return [AgentRead.model_validate(agent) for agent in agents]


@router.get("/by-role/{role}", response_model=AgentRead)
async def get_agent_by_role_route(
    role: AgentRole,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AgentRead:
    agent = await pick_next_owner(session, role)
    return AgentRead.model_validate(agent)


@router.get("/{agent_id}", response_model=AgentRead)
async def get_agent_route(
    agent_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AgentRead:
    agent = await get_agent(session, agent_id)
    return AgentRead.model_validate(agent)

