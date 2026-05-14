"""Integration coverage for basic mailbox send, poll, ack, and reject behavior."""

from __future__ import annotations

import httpx
import pytest

from tests.integration.constants import PM_ACTOR

pytestmark = pytest.mark.integration


def _notification_payload(recipient: str = "agent:be", ticket_id: int | None = None) -> dict:
    return {
        "type": "notification",
        "recipient": recipient,
        "payload": {
            "subject": "Heads up",
            "body": "Please take a look",
            "ticket_id": ticket_id,
        },
    }


async def test_empty_mailbox(agent_be_client: httpx.AsyncClient) -> None:
    response = await agent_be_client.get("/mailbox")

    assert response.status_code == 200, response.text
    assert response.json() == []


async def test_send_notification_pm_to_agent(
    pm_client: httpx.AsyncClient,
    agent_be_client: httpx.AsyncClient,
) -> None:
    send = await pm_client.post("/mailbox/messages", json=_notification_payload())
    be_mailbox = await agent_be_client.get("/mailbox")
    pm_mailbox = await pm_client.get("/mailbox")

    assert send.status_code == 201, send.text
    assert send.json()["sender"] == PM_ACTOR
    assert be_mailbox.json()[0]["id"] == send.json()["id"]
    assert pm_mailbox.json() == []


async def test_list_mailbox_returns_oldest_first(
    pm_client: httpx.AsyncClient,
    agent_be_client: httpx.AsyncClient,
) -> None:
    first = await pm_client.post(
        "/mailbox/messages",
        json=_notification_payload(ticket_id=1),
    )
    second = await pm_client.post(
        "/mailbox/messages",
        json=_notification_payload(ticket_id=2),
    )

    response = await agent_be_client.get("/mailbox")

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert [item["id"] for item in response.json()] == [first.json()["id"], second.json()["id"]]


async def test_mailbox_limit_parameter(
    pm_client: httpx.AsyncClient,
    agent_be_client: httpx.AsyncClient,
) -> None:
    for index in range(3):
        await pm_client.post(
            "/mailbox/messages",
            json=_notification_payload(ticket_id=index),
        )

    response = await agent_be_client.get("/mailbox", params={"limit": 2})

    assert response.status_code == 200, response.text
    assert len(response.json()) == 2


async def test_ack_pending_message(
    pm_client: httpx.AsyncClient,
    agent_be_client: httpx.AsyncClient,
    db_fetch_one,
) -> None:
    message = await pm_client.post("/mailbox/messages", json=_notification_payload())

    ack = await agent_be_client.post(f"/mailbox/messages/{message.json()['id']}/ack")
    mailbox = await agent_be_client.get("/mailbox")
    row = await db_fetch_one(
        "SELECT acknowledged_at FROM mailbox_messages WHERE id = :message_id",
        {"message_id": message.json()["id"]},
    )

    assert ack.status_code == 204, ack.text
    assert mailbox.json() == []
    assert row["acknowledged_at"] is not None


async def test_ack_same_message_twice_is_idempotent(
    pm_client: httpx.AsyncClient,
    agent_be_client: httpx.AsyncClient,
) -> None:
    message = await pm_client.post("/mailbox/messages", json=_notification_payload())

    first = await agent_be_client.post(f"/mailbox/messages/{message.json()['id']}/ack")
    second = await agent_be_client.post(f"/mailbox/messages/{message.json()['id']}/ack")

    assert first.status_code == 204, first.text
    assert second.status_code == 204, second.text


async def test_reject_pending_message_with_reason(
    pm_client: httpx.AsyncClient,
    agent_be_client: httpx.AsyncClient,
    db_fetch_one,
) -> None:
    message = await pm_client.post("/mailbox/messages", json=_notification_payload())

    reject = await agent_be_client.post(
        f"/mailbox/messages/{message.json()['id']}/reject",
        json={"reason": "cannot take it"},
    )
    mailbox = await agent_be_client.get("/mailbox")
    row = await db_fetch_one(
        """
        SELECT rejected_at, rejection_reason
        FROM mailbox_messages
        WHERE id = :message_id
        """,
        {"message_id": message.json()["id"]},
    )

    assert reject.status_code == 204, reject.text
    assert mailbox.json() == []
    assert row["rejected_at"] is not None
    assert row["rejection_reason"] == "cannot take it"


async def test_reject_same_message_twice_preserves_reason(
    pm_client: httpx.AsyncClient,
    agent_be_client: httpx.AsyncClient,
    db_fetch_one,
) -> None:
    message = await pm_client.post("/mailbox/messages", json=_notification_payload())

    first = await agent_be_client.post(
        f"/mailbox/messages/{message.json()['id']}/reject",
        json={"reason": "first reason"},
    )
    second = await agent_be_client.post(
        f"/mailbox/messages/{message.json()['id']}/reject",
        json={"reason": "second reason"},
    )
    row = await db_fetch_one(
        "SELECT rejection_reason FROM mailbox_messages WHERE id = :message_id",
        {"message_id": message.json()["id"]},
    )

    assert first.status_code == 204, first.text
    assert second.status_code == 204, second.text
    assert row["rejection_reason"] == "first reason"


async def test_ack_already_rejected_message_returns_409(
    pm_client: httpx.AsyncClient,
    agent_be_client: httpx.AsyncClient,
) -> None:
    message = await pm_client.post("/mailbox/messages", json=_notification_payload())
    await agent_be_client.post(
        f"/mailbox/messages/{message.json()['id']}/reject",
        json={"reason": "no"},
    )

    response = await agent_be_client.post(f"/mailbox/messages/{message.json()['id']}/ack")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "message_state_conflict"


async def test_reject_already_acked_message_returns_409(
    pm_client: httpx.AsyncClient,
    agent_be_client: httpx.AsyncClient,
) -> None:
    message = await pm_client.post("/mailbox/messages", json=_notification_payload())
    await agent_be_client.post(f"/mailbox/messages/{message.json()['id']}/ack")

    response = await agent_be_client.post(
        f"/mailbox/messages/{message.json()['id']}/reject",
        json={"reason": "late"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "message_state_conflict"


async def test_ack_missing_message_returns_404(agent_be_client: httpx.AsyncClient) -> None:
    response = await agent_be_client.post("/mailbox/messages/999999/ack")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "mailbox_message_not_found"


async def test_ack_someone_elses_message_returns_404(
    pm_client: httpx.AsyncClient,
    agent_fe_client: httpx.AsyncClient,
) -> None:
    message = await pm_client.post("/mailbox/messages", json=_notification_payload("agent:be"))

    response = await agent_fe_client.post(f"/mailbox/messages/{message.json()['id']}/ack")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "mailbox_message_not_found"


async def test_reject_without_reason_returns_422(
    pm_client: httpx.AsyncClient,
    agent_be_client: httpx.AsyncClient,
) -> None:
    message = await pm_client.post("/mailbox/messages", json=_notification_payload())

    response = await agent_be_client.post(
        f"/mailbox/messages/{message.json()['id']}/reject",
        json={},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_send_disallowed_message_type_returns_422(
    pm_client: httpx.AsyncClient,
) -> None:
    response = await pm_client.post(
        "/mailbox/messages",
        json={
            "type": "ticket_assigned",
            "recipient": "agent:be",
            "payload": {"ticket_id": 1, "title": "x", "assigned_by": PM_ACTOR},
        },
    )

    assert response.status_code == 422


async def test_send_notification_with_ticket_id(
    pm_client: httpx.AsyncClient,
) -> None:
    response = await pm_client.post(
        "/mailbox/messages",
        json=_notification_payload(ticket_id=123),
    )

    assert response.status_code == 201, response.text
    assert response.json()["payload"]["ticket_id"] == 123


async def test_send_notification_without_ticket_id(
    pm_client: httpx.AsyncClient,
) -> None:
    response = await pm_client.post("/mailbox/messages", json=_notification_payload())

    assert response.status_code == 201, response.text
    assert response.json()["payload"]["ticket_id"] is None
