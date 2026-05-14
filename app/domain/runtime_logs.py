"""Domain operations for append-only runtime logs."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import RuntimeLogNotFoundError
from app.models.runtime_log import RuntimeLog


async def create_runtime_log(
    session: AsyncSession,
    *,
    ticket_id: int,
    agent_id: str,
    runtime_type: str,
    started_at: datetime,
    ended_at: datetime | None,
    outcome: str,
    total_turns: int | None,
    model: str | None,
    input_tokens: int | None,
    output_tokens: int | None,
    classification: str | None,
    content: str,
) -> RuntimeLog:
    log = RuntimeLog(
        ticket_id=ticket_id,
        agent_id=agent_id,
        runtime_type=runtime_type,
        started_at=started_at,
        ended_at=ended_at,
        outcome=outcome,
        total_turns=total_turns,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        classification=classification,
        content=content,
    )
    session.add(log)
    await session.flush()
    return log


async def list_runtime_logs(
    session: AsyncSession,
    *,
    ticket_id: int,
    agent_id: str | None = None,
) -> list[RuntimeLog]:
    conditions = [RuntimeLog.ticket_id == ticket_id]
    if agent_id is not None:
        conditions.append(RuntimeLog.agent_id == agent_id)
    result = await session.execute(
        select(RuntimeLog)
        .where(and_(*conditions))
        .order_by(RuntimeLog.created_at.asc(), RuntimeLog.id.asc())
    )
    return list(result.scalars().all())


async def get_runtime_log(session: AsyncSession, log_id: int) -> RuntimeLog:
    log = await session.get(RuntimeLog, log_id)
    if log is None:
        raise RuntimeLogNotFoundError(log_id)
    return log
