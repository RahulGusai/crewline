"""Integration coverage for mailbox authorization boundaries."""

from __future__ import annotations

import httpx
import pytest

from tests.integration.constants import PM_ACTOR

pytestmark = pytest.mark.integration


def _notification(recipient: str) -> dict:
    return {
        "type": "notification",
        "recipient": recipient,
        "payload": {"subject": "FYI", "body": "message"},
    }


async def test_agent_reads_own_mailbox(
    pm_client: httpx.AsyncClient,
    agent_be_client: httpx.AsyncClient,
) -> None:
    send = await pm_client.post("/mailbox/messages", json=_notification("agent:be"))

    response = await agent_be_client.get("/mailbox")

    assert send.status_code == 201, send.text
    assert response.status_code == 200, response.text
    assert [item["id"] for item in response.json()] == [send.json()["id"]]


async def test_agent_mailbox_does_not_include_pm_messages(
    pm_client: httpx.AsyncClient,
    agent_be_client: httpx.AsyncClient,
) -> None:
    await agent_be_client.post("/mailbox/messages", json=_notification(PM_ACTOR))
    own = await pm_client.post("/mailbox/messages", json=_notification("agent:be"))

    response = await agent_be_client.get("/mailbox")

    assert own.status_code == 201, own.text
    assert [item["id"] for item in response.json()] == [own.json()["id"]]


async def test_pm_reads_own_mailbox(
    pm_client: httpx.AsyncClient,
    agent_be_client: httpx.AsyncClient,
) -> None:
    send = await agent_be_client.post("/mailbox/messages", json=_notification(PM_ACTOR))

    response = await pm_client.get("/mailbox")

    assert send.status_code == 201, send.text
    assert response.status_code == 200, response.text
    assert response.json()[0]["id"] == send.json()["id"]


@pytest.mark.parametrize("message_type", ["ticket_assigned", "ticket_cancelled"])
async def test_system_fired_message_types_are_rejected(
    pm_client: httpx.AsyncClient,
    message_type: str,
) -> None:
    response = await pm_client.post(
        "/mailbox/messages",
        json={"type": message_type, "recipient": "agent:be", "payload": {}},
    )

    assert response.status_code == 422
