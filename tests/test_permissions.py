"""Unit coverage for authorization helpers."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.auth.permissions import require_agent_ticket_read_access, require_ticket_read_access
from app.domain.actor import Actor
from app.domain.exceptions import ActorNotPermittedError
from app.enums import ActorKind


@pytest.mark.asyncio
async def test_agent_can_read_ticket_it_does_not_own() -> None:
    actor = Actor(kind=ActorKind.AGENT, id="sentinel", raw="agent:sentinel")
    ticket = SimpleNamespace(owner_agent_id="cortex")

    await require_ticket_read_access(
        SimpleNamespace(),  # type: ignore[arg-type]
        actor,
        ticket,  # type: ignore[arg-type]
        "read ticket 123",
    )


@pytest.mark.asyncio
async def test_non_owner_agent_can_read_ticket_it_does_not_own() -> None:
    actor = Actor(kind=ActorKind.AGENT, id="cortex", raw="agent:cortex")
    ticket = SimpleNamespace(owner_agent_id="lumen")

    await require_ticket_read_access(
        SimpleNamespace(),  # type: ignore[arg-type]
        actor,
        ticket,  # type: ignore[arg-type]
        "read ticket 123",
    )


@pytest.mark.asyncio
async def test_agent_ticket_read_access_rejects_human_actor() -> None:
    actor = Actor(kind=ActorKind.HUMAN, id="pm", raw="human:pm")
    ticket = SimpleNamespace(owner_agent_id="cortex")

    with pytest.raises(ActorNotPermittedError):
        await require_agent_ticket_read_access(
            SimpleNamespace(),  # type: ignore[arg-type]
            actor,
            ticket,  # type: ignore[arg-type]
            "mint GitHub token for ticket 123",
        )
