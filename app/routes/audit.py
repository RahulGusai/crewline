"""HTTP routes for ticket audit log reads."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_actor
from app.auth.permissions import require_ticket_read_access
from app.db import get_session
from app.domain.actor import Actor
from app.domain.audit import get_ticket_audit_log
from app.domain.tickets import get_ticket
from app.schemas.audit import AuditEntryRead

router = APIRouter(prefix="/tickets", tags=["audit"])


@router.get("/{ticket_id}/audit", response_model=list[AuditEntryRead])
async def get_audit_route(
    ticket_id: int,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[AuditEntryRead]:
    ticket = await get_ticket(session, ticket_id)
    await require_ticket_read_access(session, actor, ticket, f"read audit for ticket {ticket_id}")

    entries = await get_ticket_audit_log(session, ticket_id)
    return [AuditEntryRead.model_validate(entry) for entry in entries]
