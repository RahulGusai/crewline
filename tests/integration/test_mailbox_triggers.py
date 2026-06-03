"""Integration coverage for mailbox messages fired by ticket domain events."""

from __future__ import annotations

import httpx
import pytest

from tests.integration.constants import PM_ACTOR

pytestmark = pytest.mark.integration


async def test_create_ticket_with_owner_fires_ticket_assigned(
    create_ticket,
    db_fetch_one,
) -> None:
    ticket = await create_ticket(title="assigned", owner_agent_id="cortex")

    message = await db_fetch_one(
        "SELECT type, recipient, payload FROM mailbox_messages WHERE payload->>'ticket_id' = :ticket_id",
        {"ticket_id": str(ticket["id"])},
    )

    assert message["type"] == "ticket_assigned"
    assert message["recipient"] == "agent:cortex"
    assert message["payload"]["assigned_by"] == PM_ACTOR


async def test_create_ticket_without_owner_fires_no_mailbox_messages(
    create_ticket,
    db_fetch_one,
) -> None:
    await create_ticket(owner_agent_id=None)

    row = await db_fetch_one("SELECT count(*) AS count FROM mailbox_messages")

    assert row["count"] == 0


async def test_reassign_to_new_owner_fires_unassigned_and_assigned(
    create_ticket,
    pm_client: httpx.AsyncClient,
    db_fetch_all,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")

    response = await pm_client.post(
        f"/tickets/{ticket['id']}/assign",
        json={"new_owner_agent_id": "lumen"},
    )
    messages = await db_fetch_all(
        "SELECT type, recipient FROM mailbox_messages ORDER BY id",
    )

    assert response.status_code == 200, response.text
    assert {"type": "ticket_unassigned", "recipient": "agent:cortex"} in messages
    assert {"type": "ticket_assigned", "recipient": "agent:lumen"} in messages


async def test_assign_unassigned_ticket_fires_only_assigned(
    create_ticket,
    pm_client: httpx.AsyncClient,
    db_fetch_all,
) -> None:
    ticket = await create_ticket(owner_agent_id=None)

    response = await pm_client.post(
        f"/tickets/{ticket['id']}/assign",
        json={"new_owner_agent_id": "cortex"},
    )
    messages = await db_fetch_all("SELECT type, recipient FROM mailbox_messages ORDER BY id")

    assert response.status_code == 200, response.text
    assert messages == [{"type": "ticket_assigned", "recipient": "agent:cortex"}]


async def test_cancel_ticket_with_owner_fires_cancelled_message(
    create_ticket,
    move_ticket,
    pm_client: httpx.AsyncClient,
    db_fetch_one,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")

    response = await move_ticket(pm_client, ticket["id"], "CANCELLED", "out of scope", True)
    message = await db_fetch_one(
        "SELECT type, recipient, payload FROM mailbox_messages WHERE type = 'ticket_cancelled'",
    )

    assert response.status_code == 200, response.text
    assert message["type"] == "ticket_cancelled"
    assert message["recipient"] == "agent:cortex"
    assert message["payload"]["reason"] == "out of scope"


async def test_cancel_unassigned_ticket_fires_no_cancel_message(
    create_ticket,
    move_ticket,
    pm_client: httpx.AsyncClient,
    db_fetch_one,
) -> None:
    ticket = await create_ticket(owner_agent_id=None)

    response = await move_ticket(pm_client, ticket["id"], "CANCELLED", "out of scope", True)
    row = await db_fetch_one(
        "SELECT count(*) AS count FROM mailbox_messages WHERE type = 'ticket_cancelled'",
    )

    assert response.status_code == 200, response.text
    assert row["count"] == 0


async def test_in_progress_to_in_qa_fires_review_requested(
    create_ticket,
    move_ticket,
    agent_be_client: httpx.AsyncClient,
    db_fetch_one,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")
    await move_ticket(agent_be_client, ticket["id"], "IN_PROGRESS")

    response = await move_ticket(agent_be_client, ticket["id"], "IN_QA")
    message = await db_fetch_one(
        "SELECT type, recipient, sender, payload FROM mailbox_messages WHERE type = 'ticket_review_requested'",
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "IN_QA"
    assert message["type"] == "ticket_review_requested"
    assert message["recipient"] == "agent:sentinel"
    assert message["sender"] == "system:system"
    assert message["payload"]["requested_by"] == "system:system"


async def test_other_transitions_fire_no_mailbox_messages(
    create_ticket,
    move_ticket,
    agent_be_client: httpx.AsyncClient,
    db_fetch_one,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")
    before = await db_fetch_one("SELECT count(*) AS count FROM mailbox_messages")

    response = await move_ticket(agent_be_client, ticket["id"], "IN_PROGRESS")
    after = await db_fetch_one("SELECT count(*) AS count FROM mailbox_messages")

    assert response.status_code == 200, response.text
    assert after["count"] == before["count"]


async def test_auto_fired_message_sender_matches_triggering_actor(
    create_ticket,
    move_ticket,
    pm_client: httpx.AsyncClient,
    db_fetch_one,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")

    response = await move_ticket(pm_client, ticket["id"], "CANCELLED", "sender check", True)
    message = await db_fetch_one(
        "SELECT sender FROM mailbox_messages WHERE type = 'ticket_cancelled'",
    )

    assert response.status_code == 200, response.text
    assert message["sender"] == PM_ACTOR


@pytest.mark.skip(reason="Requires a deliberate mid-transaction failure hook that is not exposed")
async def test_mailbox_message_and_ticket_update_atomic() -> None:
    """Skipped until the service exposes a clean integration failure hook."""
