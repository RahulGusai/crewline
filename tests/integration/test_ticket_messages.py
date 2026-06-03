"""Integration coverage for per-ticket mailbox message history."""

from __future__ import annotations

import httpx
import pytest

from tests.integration.constants import PM_ACTOR

pytestmark = pytest.mark.integration


def _notification_payload(
    recipient: str,
    *,
    ticket_id: int | None,
    subject: str = "FYI",
) -> dict:
    return {
        "type": "notification",
        "recipient": recipient,
        "payload": {
            "subject": subject,
            "body": "message",
            "ticket_id": ticket_id,
        },
    }


def _rpc_request_payload(recipient: str, *, ticket_id: int) -> dict:
    return {
        "type": "rpc_request",
        "recipient": recipient,
        "payload": {
            "subject": "Question",
            "body": "Can you confirm?",
            "ticket_id": ticket_id,
        },
    }


async def test_pm_lists_all_messages_for_ticket_oldest_first(
    create_ticket,
    pm_client: httpx.AsyncClient,
    agent_be_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")
    rpc = await pm_client.post("/mailbox/messages", json=_rpc_request_payload("agent:cortex", ticket_id=ticket["id"]))
    note = await agent_be_client.post(
        "/mailbox/messages",
        json=_notification_payload(PM_ACTOR, ticket_id=ticket["id"], subject="Update"),
    )

    response = await pm_client.get(f"/tickets/{ticket['id']}/messages")

    assert rpc.status_code == 201, rpc.text
    assert note.status_code == 201, note.text
    assert response.status_code == 200, response.text
    messages = response.json()
    assert [message["type"] for message in messages] == [
        "ticket_assigned",
        "rpc_request",
        "notification",
    ]
    assert [message["id"] for message in messages] == sorted(message["id"] for message in messages)


async def test_agent_owner_lists_only_messages_they_sent_or_received(
    create_ticket,
    pm_client: httpx.AsyncClient,
    agent_be_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")
    visible = await pm_client.post(
        "/mailbox/messages",
        json=_notification_payload("agent:cortex", ticket_id=ticket["id"], subject="Visible"),
    )
    hidden = await pm_client.post(
        "/mailbox/messages",
        json=_notification_payload("agent:lumen", ticket_id=ticket["id"], subject="Hidden"),
    )

    response = await agent_be_client.get(f"/tickets/{ticket['id']}/messages")

    assert visible.status_code == 201, visible.text
    assert hidden.status_code == 201, hidden.text
    assert response.status_code == 200, response.text
    ids = [message["id"] for message in response.json()]
    assert visible.json()["id"] in ids
    assert hidden.json()["id"] not in ids
    assert all(
        message["sender"] == "agent:cortex" or message["recipient"] == "agent:cortex"
        for message in response.json()
    )


async def test_agent_non_owner_can_read_ticket_messages(
    create_ticket,
    agent_fe_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")

    response = await agent_fe_client.get(f"/tickets/{ticket['id']}/messages")

    assert response.status_code == 200, response.text


async def test_qa_agent_lists_messages_for_other_agent_ticket(
    create_ticket,
    agent_qa_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")

    response = await agent_qa_client.get(f"/tickets/{ticket['id']}/messages")

    assert response.status_code == 200, response.text


async def test_nonexistent_ticket_messages_returns_404(pm_client: httpx.AsyncClient) -> None:
    response = await pm_client.get("/tickets/999999/messages")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ticket_not_found"


async def test_ticket_messages_include_acked_and_rejected_messages(
    create_ticket,
    pm_client: httpx.AsyncClient,
    agent_be_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")
    acked = await pm_client.post(
        "/mailbox/messages",
        json=_notification_payload("agent:cortex", ticket_id=ticket["id"], subject="Ack me"),
    )
    rejected = await pm_client.post(
        "/mailbox/messages",
        json=_notification_payload("agent:cortex", ticket_id=ticket["id"], subject="Reject me"),
    )
    ack = await agent_be_client.post(f"/mailbox/messages/{acked.json()['id']}/ack")
    reject = await agent_be_client.post(
        f"/mailbox/messages/{rejected.json()['id']}/reject",
        json={"reason": "not relevant"},
    )

    response = await pm_client.get(f"/tickets/{ticket['id']}/messages")

    assert ack.status_code == 204, ack.text
    assert reject.status_code == 204, reject.text
    assert response.status_code == 200, response.text
    ids = [message["id"] for message in response.json()]
    assert acked.json()["id"] in ids
    assert rejected.json()["id"] in ids


async def test_ticket_messages_exclude_notifications_without_ticket_id(
    create_ticket,
    pm_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")
    ticketless = await pm_client.post(
        "/mailbox/messages",
        json=_notification_payload("agent:cortex", ticket_id=None, subject="General"),
    )

    response = await pm_client.get(f"/tickets/{ticket['id']}/messages")

    assert ticketless.status_code == 201, ticketless.text
    assert response.status_code == 200, response.text
    assert ticketless.json()["id"] not in [message["id"] for message in response.json()]


async def test_ticket_messages_requires_auth(
    create_ticket,
    anonymous_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")

    response = await anonymous_client.get(f"/tickets/{ticket['id']}/messages")

    assert response.status_code == 401


async def test_rpc_response_included_in_ticket_messages(
    create_ticket,
    pm_client: httpx.AsyncClient,
    agent_be_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(title="rpc pairing", owner_agent_id="cortex")
    request = await agent_be_client.post(
        "/mailbox/messages",
        json=_rpc_request_payload(PM_ACTOR, ticket_id=ticket["id"]),
    )
    response_message = await pm_client.post(
        "/mailbox/messages",
        json={
            "type": "rpc_response",
            "recipient": "agent:cortex",
            "correlation_id": request.json()["id"],
            "payload": {"body": "Answer", "outcome": "answered"},
        },
    )

    response = await pm_client.get(f"/tickets/{ticket['id']}/messages")

    assert request.status_code == 201, request.text
    assert response_message.status_code == 201, response_message.text
    assert response.status_code == 200, response.text
    messages = response.json()
    types = [message["type"] for message in messages]
    assert "rpc_request" in types
    assert "rpc_response" in types
    rpc_response = next(message for message in messages if message["type"] == "rpc_response")
    assert rpc_response["correlation_id"] == request.json()["id"]


async def test_agent_owner_sees_own_correlated_rpc_response(
    create_ticket,
    pm_client: httpx.AsyncClient,
    agent_be_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(title="agent rpc pairing", owner_agent_id="cortex")
    request = await agent_be_client.post(
        "/mailbox/messages",
        json=_rpc_request_payload(PM_ACTOR, ticket_id=ticket["id"]),
    )
    response_message = await pm_client.post(
        "/mailbox/messages",
        json={
            "type": "rpc_response",
            "recipient": "agent:cortex",
            "correlation_id": request.json()["id"],
            "payload": {"body": "Answer", "outcome": "answered"},
        },
    )

    response = await agent_be_client.get(f"/tickets/{ticket['id']}/messages")

    assert request.status_code == 201, request.text
    assert response_message.status_code == 201, response_message.text
    assert response.status_code == 200, response.text
    ids = [message["id"] for message in response.json()]
    assert request.json()["id"] in ids
    assert response_message.json()["id"] in ids


async def test_agent_filtering_hides_other_correlated_rpc_response(
    create_ticket,
    pm_client: httpx.AsyncClient,
    agent_be_client: httpx.AsyncClient,
    agent_fe_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(title="hidden rpc pairing", owner_agent_id="cortex")
    request = await pm_client.post(
        "/mailbox/messages",
        json=_rpc_request_payload("agent:lumen", ticket_id=ticket["id"]),
    )
    response_message = await agent_fe_client.post(
        "/mailbox/messages",
        json={
            "type": "rpc_response",
            "recipient": PM_ACTOR,
            "correlation_id": request.json()["id"],
            "payload": {"body": "Private answer", "outcome": "answered"},
        },
    )

    response = await agent_be_client.get(f"/tickets/{ticket['id']}/messages")

    assert request.status_code == 201, request.text
    assert response_message.status_code == 201, response_message.text
    assert response.status_code == 200, response.text
    ids = [message["id"] for message in response.json()]
    assert request.json()["id"] not in ids
    assert response_message.json()["id"] not in ids
