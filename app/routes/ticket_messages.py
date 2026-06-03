"""HTTP route for per-ticket mailbox message history."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_actor
from app.auth.permissions import require_ticket_read_access
from app.db import get_session
from app.domain.actor import Actor
from app.domain.mailbox import list_messages_for_ticket
from app.domain.tickets import get_ticket
from app.schemas.mailbox import MailboxMessageRead

router = APIRouter(prefix="/tickets", tags=["mailbox"])


@router.get("/{ticket_id}/messages", response_model=list[MailboxMessageRead])
async def list_ticket_messages_route(
    ticket_id: int,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[MailboxMessageRead]:
    """Return mailbox messages tied to a ticket, ordered oldest-first."""
    ticket = await get_ticket(session, ticket_id)
    await require_ticket_read_access(session, actor, ticket, f"list messages for ticket {ticket_id}")

    messages = await list_messages_for_ticket(
        session,
        ticket_id=ticket_id,
        actor=actor,
    )
    return [MailboxMessageRead.model_validate(message) for message in messages]
