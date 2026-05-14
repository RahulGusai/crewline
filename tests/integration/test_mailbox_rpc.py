"""Integration coverage for mailbox RPC request/response behavior."""

from __future__ import annotations

import httpx
import pytest

from tests.integration.constants import PM_ACTOR

pytestmark = pytest.mark.integration


def _rpc_request_payload(
    recipient: str = "agent:be",
    ticket_id: int | None = 1,
    subject: str | None = "Question",
    body: str | None = "Can you confirm?",
) -> dict:
    payload: dict[str, object] = {}
    if subject is not None:
        payload["subject"] = subject
    if body is not None:
        payload["body"] = body
    if ticket_id is not None:
        payload["ticket_id"] = ticket_id
    return {"type": "rpc_request", "recipient": recipient, "payload": payload}


def _rpc_response_payload(
    recipient: str,
    correlation_id: int,
    outcome: str = "answered",
) -> dict:
    return {
        "type": "rpc_response",
        "recipient": recipient,
        "correlation_id": correlation_id,
        "payload": {"body": "Done", "outcome": outcome},
    }


@pytest.mark.parametrize(
    "missing",
    ["subject", "body", "ticket_id"],
)
async def test_rpc_request_requires_subject_body_and_ticket_id(
    pm_client: httpx.AsyncClient,
    missing: str,
) -> None:
    kwargs = {"subject": "Question", "body": "Body", "ticket_id": 1}
    kwargs[missing] = None

    response = await pm_client.post("/mailbox/messages", json=_rpc_request_payload(**kwargs))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_send_rpc_request_recipient_sees_message(
    pm_client: httpx.AsyncClient,
    agent_be_client: httpx.AsyncClient,
) -> None:
    send = await pm_client.post("/mailbox/messages", json=_rpc_request_payload())

    response = await agent_be_client.get("/mailbox")

    assert send.status_code == 201, send.text
    assert send.json()["requires_response"] is True
    assert response.json()[0]["id"] == send.json()["id"]


async def test_rpc_response_with_valid_correlation_id(
    pm_client: httpx.AsyncClient,
    agent_be_client: httpx.AsyncClient,
) -> None:
    request = await pm_client.post("/mailbox/messages", json=_rpc_request_payload())

    response = await agent_be_client.post(
        "/mailbox/messages",
        json=_rpc_response_payload(PM_ACTOR, request.json()["id"]),
    )
    pm_mailbox = await pm_client.get("/mailbox")

    assert response.status_code == 201, response.text
    assert response.json()["correlation_id"] == request.json()["id"]
    assert pm_mailbox.json()[0]["id"] == response.json()["id"]


async def test_rpc_response_with_nonexistent_correlation_id_returns_422(
    agent_be_client: httpx.AsyncClient,
) -> None:
    response = await agent_be_client.post(
        "/mailbox/messages",
        json=_rpc_response_payload(PM_ACTOR, 999999),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "correlation_id_mismatch"


async def test_rpc_response_to_non_rpc_request_returns_422(
    pm_client: httpx.AsyncClient,
    agent_be_client: httpx.AsyncClient,
) -> None:
    notification = await pm_client.post(
        "/mailbox/messages",
        json={
            "type": "notification",
            "recipient": "agent:be",
            "payload": {"subject": "FYI", "body": "hello"},
        },
    )

    response = await agent_be_client.post(
        "/mailbox/messages",
        json=_rpc_response_payload(PM_ACTOR, notification.json()["id"]),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "correlation_id_mismatch"


async def test_rpc_response_recipient_must_be_original_sender(
    pm_client: httpx.AsyncClient,
    agent_be_client: httpx.AsyncClient,
) -> None:
    request = await pm_client.post("/mailbox/messages", json=_rpc_request_payload())

    response = await agent_be_client.post(
        "/mailbox/messages",
        json=_rpc_response_payload("agent:qa", request.json()["id"]),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "correlation_id_mismatch"


async def test_second_rpc_response_to_same_request_returns_422(
    pm_client: httpx.AsyncClient,
    agent_be_client: httpx.AsyncClient,
) -> None:
    request = await pm_client.post("/mailbox/messages", json=_rpc_request_payload())
    first = await agent_be_client.post(
        "/mailbox/messages",
        json=_rpc_response_payload(PM_ACTOR, request.json()["id"]),
    )

    second = await agent_be_client.post(
        "/mailbox/messages",
        json=_rpc_response_payload(PM_ACTOR, request.json()["id"]),
    )

    assert first.status_code == 201, first.text
    assert second.status_code == 422
    assert second.json()["error"]["code"] == "correlation_id_mismatch"


@pytest.mark.parametrize("outcome", ["answered", "declined"])
async def test_rpc_response_outcomes_are_accepted(
    pm_client: httpx.AsyncClient,
    agent_be_client: httpx.AsyncClient,
    outcome: str,
) -> None:
    request = await pm_client.post("/mailbox/messages", json=_rpc_request_payload())

    response = await agent_be_client.post(
        "/mailbox/messages",
        json=_rpc_response_payload(PM_ACTOR, request.json()["id"], outcome),
    )

    assert response.status_code == 201, response.text
    assert response.json()["payload"]["outcome"] == outcome


async def test_rpc_response_invalid_outcome_returns_422(
    pm_client: httpx.AsyncClient,
    agent_be_client: httpx.AsyncClient,
) -> None:
    request = await pm_client.post("/mailbox/messages", json=_rpc_request_payload())

    response = await agent_be_client.post(
        "/mailbox/messages",
        json=_rpc_response_payload(PM_ACTOR, request.json()["id"], "maybe"),
    )

    assert response.status_code == 422


async def test_agent_sends_rpc_request_to_pm(
    agent_be_client: httpx.AsyncClient,
    pm_client: httpx.AsyncClient,
) -> None:
    send = await agent_be_client.post(
        "/mailbox/messages",
        json=_rpc_request_payload(recipient=PM_ACTOR),
    )
    mailbox = await pm_client.get("/mailbox")

    assert send.status_code == 201, send.text
    assert mailbox.json()[0]["id"] == send.json()["id"]


async def test_pm_sends_rpc_request_to_agent(
    pm_client: httpx.AsyncClient,
    agent_be_client: httpx.AsyncClient,
) -> None:
    send = await pm_client.post("/mailbox/messages", json=_rpc_request_payload("agent:be"))
    mailbox = await agent_be_client.get("/mailbox")

    assert send.status_code == 201, send.text
    assert mailbox.json()[0]["id"] == send.json()["id"]


async def test_agent_sends_rpc_request_to_another_agent(
    agent_be_client: httpx.AsyncClient,
    agent_fe_client: httpx.AsyncClient,
) -> None:
    send = await agent_be_client.post(
        "/mailbox/messages",
        json=_rpc_request_payload(recipient="agent:fe"),
    )
    mailbox = await agent_fe_client.get("/mailbox")

    assert send.status_code == 201, send.text
    assert mailbox.json()[0]["id"] == send.json()["id"]
