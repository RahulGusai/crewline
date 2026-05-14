"""Audit log query functions."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ticket_audit_log import TicketAuditLog


async def get_ticket_audit_log(
    session: AsyncSession,
    ticket_id: int,
) -> list[TicketAuditLog]:
    """Return all audit rows for a ticket, oldest first."""
    stmt = (
        select(TicketAuditLog)
        .where(TicketAuditLog.ticket_id == ticket_id)
        .order_by(TicketAuditLog.occurred_at.asc(), TicketAuditLog.id.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())

