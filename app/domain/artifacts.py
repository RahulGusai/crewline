"""Artifact operations - append-only notes attached to tickets."""

from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.actor import parse_actor
from app.domain.tickets import _get_ticket_for_update
from app.models.ticket_artifact import TicketArtifact

logger = structlog.get_logger(__name__)


async def add_artifact(
    session: AsyncSession,
    *,
    ticket_id: int,
    artifact_type: str,
    author: str,
    content: str,
) -> TicketArtifact:
    """Insert an artifact row."""
    parse_actor(author)
    await _get_ticket_for_update(session, ticket_id)

    artifact = TicketArtifact(
        ticket_id=ticket_id,
        artifact_type=artifact_type,
        author=author,
        content=content,
    )
    session.add(artifact)
    await session.flush()

    logger.info(
        "artifact.added",
        ticket_id=ticket_id,
        artifact_id=artifact.id,
        artifact_type=artifact_type,
        author=author,
    )
    return artifact


async def list_artifacts(
    session: AsyncSession,
    ticket_id: int,
) -> list[TicketArtifact]:
    """Return all artifacts for a ticket, oldest first."""
    stmt = (
        select(TicketArtifact)
        .where(TicketArtifact.ticket_id == ticket_id)
        .order_by(TicketArtifact.created_at.asc(), TicketArtifact.id.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())

