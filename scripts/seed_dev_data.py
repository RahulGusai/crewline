"""Dev-data seeding script.

Usage:
    uv run python -m scripts.seed_dev_data

The script must be idempotent: running it twice should not duplicate data.
"""

from __future__ import annotations

import asyncio

import structlog
from sqlalchemy import select

from app.config import get_settings
from app.db import session_scope
from app.domain.tickets import create_ticket, transition_ticket
from app.enums import TicketStatus
from app.logging_config import configure_logging
from app.models.ticket import Ticket

logger = structlog.get_logger(__name__)

SEED_MARKER_KEY = "_dev_seed"
SEED_MARKER_VALUE = "v1"
SEED_REPO = "local/crewline"


async def main() -> None:
    settings = get_settings()
    configure_logging(settings)

    async with session_scope() as session:
        existing = await session.execute(
            select(Ticket)
            .where(Ticket.metadata_[SEED_MARKER_KEY].astext == SEED_MARKER_VALUE)
            .limit(1)
        )
        if existing.scalar_one_or_none() is not None:
            logger.info("seed_dev_data.skipped", reason="already seeded")
            return

        await create_ticket(
            session=session,
            title="[seed] Implement /healthz endpoint",
            description="Add a basic liveness check endpoint.",
            created_by="human:pm",
            owner_agent_id="be",
            repo_full_name=SEED_REPO,
            metadata={SEED_MARKER_KEY: SEED_MARKER_VALUE},
        )

        ticket2 = await create_ticket(
            session=session,
            title="[seed] Build login form",
            description="Email + password fields, basic validation.",
            created_by="human:pm",
            owner_agent_id="fe",
            repo_full_name=SEED_REPO,
            metadata={SEED_MARKER_KEY: SEED_MARKER_VALUE},
        )
        await transition_ticket(
            session=session,
            ticket_id=ticket2.id,
            to_status=TicketStatus.IN_PROGRESS,
            actor="agent:fe",
        )

        ticket3 = await create_ticket(
            session=session,
            title="[seed] Choose caching strategy",
            description="Compare Redis vs in-memory for v0.",
            created_by="human:pm",
            owner_agent_id="architect",
            repo_full_name=SEED_REPO,
            metadata={SEED_MARKER_KEY: SEED_MARKER_VALUE},
        )
        await transition_ticket(
            session=session,
            ticket_id=ticket3.id,
            to_status=TicketStatus.IN_PROGRESS,
            actor="agent:architect",
        )
        await transition_ticket(
            session=session,
            ticket_id=ticket3.id,
            to_status=TicketStatus.BLOCKED,
            actor="agent:architect",
            reason="Need PM input on cost vs performance tradeoff.",
        )

        logger.info("seed_dev_data.completed", ticket_count=3)


if __name__ == "__main__":
    asyncio.run(main())
