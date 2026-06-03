"""HTTP routes for ticket artifacts."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_actor
from app.auth.permissions import require_owned_or_qa_agent_ticket_access, require_ticket_read_access
from app.db import get_session
from app.domain.actor import Actor
from app.domain.artifacts import add_artifact, list_artifacts
from app.domain.tickets import get_ticket
from app.schemas.artifact import ArtifactCreate, ArtifactRead

router = APIRouter(prefix="/tickets", tags=["artifacts"])


@router.post(
    "/{ticket_id}/artifacts",
    status_code=status.HTTP_201_CREATED,
    response_model=ArtifactRead,
)
async def add_artifact_route(
    ticket_id: int,
    payload: ArtifactCreate,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ArtifactRead:
    ticket = await get_ticket(session, ticket_id)
    await require_owned_or_qa_agent_ticket_access(
        session,
        actor,
        ticket,
        f"add artifact to ticket {ticket_id}",
    )

    artifact = await add_artifact(
        session=session,
        ticket_id=ticket_id,
        artifact_type=payload.artifact_type,
        author=actor.raw,
        content=payload.content,
    )
    return ArtifactRead.model_validate(artifact)


@router.get("/{ticket_id}/artifacts", response_model=list[ArtifactRead])
async def list_artifacts_route(
    ticket_id: int,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[ArtifactRead]:
    ticket = await get_ticket(session, ticket_id)
    await require_ticket_read_access(session, actor, ticket, f"list artifacts on ticket {ticket_id}")

    artifacts = await list_artifacts(session, ticket_id)
    return [ArtifactRead.model_validate(artifact) for artifact in artifacts]
