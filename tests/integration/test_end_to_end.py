"""End-to-end integration flows across tickets, audit, mailbox, artifacts, and auth."""

from __future__ import annotations

import httpx
import pytest

from tests.integration.constants import DEFAULT_REPO, PM_ACTOR

pytestmark = pytest.mark.integration


async def _transition(
    client: httpx.AsyncClient,
    ticket_id: int,
    to_status: str,
    reason: str | None = None,
    pm_override: bool = False,
) -> httpx.Response:
    payload: dict[str, object] = {"to_status": to_status}
    if reason is not None:
        payload["reason"] = reason
    if pm_override:
        payload["pm_override"] = True
    return await client.post(f"/tickets/{ticket_id}/transitions", json=payload)


async def _message_id(mailbox: httpx.Response, message_type: str) -> int:
    for message in mailbox.json():
        if message["type"] == message_type:
            return int(message["id"])
    raise AssertionError(f"message type {message_type!r} not found")


async def test_flow_a_happy_path_ticket_lifecycle(
    pm_client: httpx.AsyncClient,
    agent_be_client: httpx.AsyncClient,
    agent_qa_client: httpx.AsyncClient,
    db_fetch_one,
) -> None:
    created = await pm_client.post(
        "/tickets",
        json={"title": "happy path", "owner_agent_id": "cortex", "repo_full_name": DEFAULT_REPO},
    )
    ticket_id = created.json()["id"]
    be_mailbox = await agent_be_client.get("/mailbox")
    assigned_id = await _message_id(be_mailbox, "ticket_assigned")
    ack_assigned = await agent_be_client.post(f"/mailbox/messages/{assigned_id}/ack")

    started = await _transition(agent_be_client, ticket_id, "IN_PROGRESS")
    artifact = await agent_be_client.post(
        f"/tickets/{ticket_id}/artifacts",
        json={"artifact_type": "implementation", "content": "built"},
    )
    ready = await _transition(agent_be_client, ticket_id, "IN_QA")
    qa_mailbox = await agent_qa_client.get("/mailbox")
    review_id = await _message_id(qa_mailbox, "ticket_review_requested")
    ack_review = await agent_qa_client.post(f"/mailbox/messages/{review_id}/ack")
    done = await _transition(agent_qa_client, ticket_id, "DONE")
    audit = await db_fetch_one(
        "SELECT count(*) AS count FROM ticket_audit_log WHERE ticket_id = :ticket_id",
        {"ticket_id": ticket_id},
    )

    assert created.status_code == 201, created.text
    assert ack_assigned.status_code == 204, ack_assigned.text
    assert started.status_code == 200, started.text
    assert artifact.status_code == 201, artifact.text
    assert ready.status_code == 200, ready.text
    assert ready.json()["status"] == "IN_QA"
    assert ack_review.status_code == 204, ack_review.text
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "DONE"
    assert audit["count"] >= 4


async def test_flow_b_blocked_rpc_flow(
    pm_client: httpx.AsyncClient,
    agent_be_client: httpx.AsyncClient,
) -> None:
    created = await pm_client.post(
        "/tickets",
        json={"title": "blocked flow", "owner_agent_id": "cortex", "repo_full_name": DEFAULT_REPO},
    )
    ticket_id = created.json()["id"]
    started = await _transition(agent_be_client, ticket_id, "IN_PROGRESS")
    blocked = await _transition(agent_be_client, ticket_id, "BLOCKED", "Need PM input")
    request = await agent_be_client.post(
        "/mailbox/messages",
        json={
            "type": "rpc_request",
            "recipient": PM_ACTOR,
            "payload": {
                "subject": "Need decision",
                "body": "Which direction?",
                "ticket_id": ticket_id,
            },
        },
    )
    pm_mailbox = await pm_client.get("/mailbox")
    response = await pm_client.post(
        "/mailbox/messages",
        json={
            "type": "rpc_response",
            "recipient": "agent:cortex",
            "correlation_id": request.json()["id"],
            "payload": {"body": "Use option A", "outcome": "answered"},
        },
    )
    ack_request = await pm_client.post(f"/mailbox/messages/{request.json()['id']}/ack")
    be_mailbox = await agent_be_client.get("/mailbox")
    response_id = await _message_id(be_mailbox, "rpc_response")
    ack_response = await agent_be_client.post(f"/mailbox/messages/{response_id}/ack")
    resumed = await _transition(agent_be_client, ticket_id, "IN_PROGRESS")

    assert created.status_code == 201, created.text
    assert started.status_code == 200, started.text
    assert blocked.status_code == 200, blocked.text
    assert request.status_code == 201, request.text
    assert any(item["id"] == request.json()["id"] for item in pm_mailbox.json())
    assert response.status_code == 201, response.text
    assert response.json()["correlation_id"] == request.json()["id"]
    assert ack_request.status_code == 204, ack_request.text
    assert ack_response.status_code == 204, ack_response.text
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["status"] == "IN_PROGRESS"


async def test_flow_c_qa_failure_and_rework(
    pm_client: httpx.AsyncClient,
    agent_be_client: httpx.AsyncClient,
    agent_qa_client: httpx.AsyncClient,
) -> None:
    created = await pm_client.post(
        "/tickets",
        json={"title": "sentinel failure", "owner_agent_id": "cortex", "repo_full_name": DEFAULT_REPO},
    )
    ticket_id = created.json()["id"]
    await _transition(agent_be_client, ticket_id, "IN_PROGRESS")
    await _transition(agent_be_client, ticket_id, "IN_QA")

    failed = await _transition(agent_qa_client, ticket_id, "QA_FAILED", "Needs rework")
    back_to_todo = await _transition(agent_be_client, ticket_id, "TODO")
    restarted = await _transition(agent_be_client, ticket_id, "IN_PROGRESS")
    ready = await _transition(agent_be_client, ticket_id, "IN_QA")
    done = await _transition(agent_qa_client, ticket_id, "DONE")

    assert failed.status_code == 200, failed.text
    assert back_to_todo.status_code == 200, back_to_todo.text
    assert restarted.status_code == 200, restarted.text
    assert ready.status_code == 200, ready.text
    assert ready.json()["status"] == "IN_QA"
    assert done.status_code == 200, done.text
    assert done.json()["owner_agent_id"] == "cortex"


async def test_flow_d_cancellation_is_terminal(
    pm_client: httpx.AsyncClient,
    agent_be_client: httpx.AsyncClient,
) -> None:
    created = await pm_client.post(
        "/tickets",
        json={"title": "cancelled", "owner_agent_id": "cortex", "repo_full_name": DEFAULT_REPO},
    )
    ticket_id = created.json()["id"]
    started = await _transition(agent_be_client, ticket_id, "IN_PROGRESS")
    cancelled = await _transition(pm_client, ticket_id, "CANCELLED", "No longer needed", True)
    be_mailbox = await agent_be_client.get("/mailbox")
    cancel_id = await _message_id(be_mailbox, "ticket_cancelled")
    after_cancel = await _transition(agent_be_client, ticket_id, "IN_PROGRESS")

    assert started.status_code == 200, started.text
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "CANCELLED"
    assert cancel_id > 0
    assert after_cancel.status_code == 409
    assert after_cancel.json()["error"]["code"] == "invalid_transition"


async def test_flow_e_reassignment_to_fe_then_completion(
    pm_client: httpx.AsyncClient,
    agent_be_client: httpx.AsyncClient,
    agent_fe_client: httpx.AsyncClient,
    agent_qa_client: httpx.AsyncClient,
    db_fetch_all,
) -> None:
    created = await pm_client.post(
        "/tickets",
        json={"title": "reassignment", "owner_agent_id": "cortex", "repo_full_name": DEFAULT_REPO},
    )
    ticket_id = created.json()["id"]
    be_initial = await agent_be_client.get("/mailbox")
    initial_id = await _message_id(be_initial, "ticket_assigned")
    await agent_be_client.post(f"/mailbox/messages/{initial_id}/ack")

    reassigned = await pm_client.post(
        f"/tickets/{ticket_id}/assign",
        json={"new_owner_agent_id": "lumen"},
    )
    be_mailbox = await agent_be_client.get("/mailbox")
    fe_mailbox = await agent_fe_client.get("/mailbox")
    unassigned_id = await _message_id(be_mailbox, "ticket_unassigned")
    fe_assigned_id = await _message_id(fe_mailbox, "ticket_assigned")
    started = await _transition(agent_fe_client, ticket_id, "IN_PROGRESS")
    ready = await _transition(agent_fe_client, ticket_id, "IN_QA")
    done = await _transition(agent_qa_client, ticket_id, "DONE")
    owner_audit = await db_fetch_all(
        """
        SELECT from_owner, to_owner
        FROM ticket_audit_log
        WHERE ticket_id = :ticket_id AND to_owner IS NOT NULL
        ORDER BY id
        """,
        {"ticket_id": ticket_id},
    )

    assert reassigned.status_code == 200, reassigned.text
    assert unassigned_id > 0
    assert fe_assigned_id > 0
    assert started.status_code == 200, started.text
    assert ready.status_code == 200, ready.text
    assert ready.json()["status"] == "IN_QA"
    assert done.status_code == 200, done.text
    assert {"from_owner": "cortex", "to_owner": "lumen"} in owner_audit
