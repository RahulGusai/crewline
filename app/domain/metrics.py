"""Computed time-tracking metrics for tickets, derived from the audit log."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.tickets import get_ticket


@dataclass(frozen=True)
class TicketMetrics:
    ticket_id: int
    started_at: datetime | None
    completed_at: datetime | None
    total_elapsed_seconds: int | None
    blocked_seconds: int
    blocked_episodes: int


_METRICS_QUERY = text(
    """
    WITH status_events AS (
      SELECT
        ticket_id,
        to_status,
        occurred_at,
        LEAD(occurred_at) OVER (
          PARTITION BY ticket_id ORDER BY occurred_at, id
        ) AS next_occurred_at
      FROM ticket_audit_log
      WHERE ticket_id = :ticket_id
        AND to_status IS NOT NULL
        AND from_status IS DISTINCT FROM to_status
    ),
    blocked_periods AS (
      SELECT
        SUM(EXTRACT(EPOCH FROM (next_occurred_at - occurred_at)))::bigint AS blocked_seconds,
        COUNT(*) AS blocked_episodes
      FROM status_events
      WHERE to_status = 'BLOCKED'
        AND next_occurred_at IS NOT NULL
    ),
    started AS (
      SELECT MIN(occurred_at) AS started_at
      FROM ticket_audit_log
      WHERE ticket_id = :ticket_id
        AND to_status = 'IN_PROGRESS'
    ),
    completed AS (
      SELECT MAX(occurred_at) AS completed_at
      FROM ticket_audit_log
      WHERE ticket_id = :ticket_id
        AND to_status = 'DONE'
    )
    SELECT
      started.started_at,
      completed.completed_at,
      COALESCE(blocked_periods.blocked_seconds, 0) AS blocked_seconds,
      COALESCE(blocked_periods.blocked_episodes, 0) AS blocked_episodes
    FROM started, completed, blocked_periods
    """
)


async def compute_ticket_metrics(
    session: AsyncSession,
    ticket_id: int,
) -> TicketMetrics:
    """Compute metrics for a single ticket from its audit log."""
    await get_ticket(session, ticket_id)

    result = await session.execute(_METRICS_QUERY, {"ticket_id": ticket_id})
    row = result.one()
    started_at: datetime | None = row.started_at
    completed_at: datetime | None = row.completed_at
    blocked_seconds = int(row.blocked_seconds)
    blocked_episodes = int(row.blocked_episodes)

    total_elapsed_seconds: int | None = None
    if started_at is not None and completed_at is not None:
        total_elapsed_seconds = int((completed_at - started_at).total_seconds())

    return TicketMetrics(
        ticket_id=ticket_id,
        started_at=started_at,
        completed_at=completed_at,
        total_elapsed_seconds=total_elapsed_seconds,
        blocked_seconds=blocked_seconds,
        blocked_episodes=blocked_episodes,
    )

