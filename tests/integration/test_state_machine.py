"""Integration coverage for ticket workflow transitions."""

from __future__ import annotations

import httpx
import pytest

pytestmark = pytest.mark.integration


async def _in_qa(
    create_ticket,
    agent_be_client: httpx.AsyncClient,
    move_ticket,
) -> dict:
    ticket = await create_ticket(title="ready for sentinel", owner_agent_id="cortex")
    started = await move_ticket(agent_be_client, ticket["id"], "IN_PROGRESS")
    in_qa = await move_ticket(agent_be_client, ticket["id"], "IN_QA")
    assert started.status_code == 200, started.text
    assert in_qa.status_code == 200, in_qa.text
    return in_qa.json()


async def test_todo_to_in_progress_by_owner_agent(
    create_ticket,
    move_ticket,
    agent_be_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")

    response = await move_ticket(agent_be_client, ticket["id"], "IN_PROGRESS")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "IN_PROGRESS"


async def test_todo_to_in_progress_by_non_owner_agent(
    create_ticket,
    move_ticket,
    agent_fe_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")

    response = await move_ticket(agent_fe_client, ticket["id"], "IN_PROGRESS")

    assert response.status_code == 403


async def test_todo_to_in_progress_by_pm_not_allowed(
    create_ticket,
    move_ticket,
    pm_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")

    response = await move_ticket(pm_client, ticket["id"], "IN_PROGRESS")

    assert response.status_code == 403


async def test_todo_to_in_progress_without_reason_allowed(
    create_ticket,
    move_ticket,
    agent_be_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")

    response = await move_ticket(agent_be_client, ticket["id"], "IN_PROGRESS")

    assert response.status_code == 200, response.text


async def test_todo_to_blocked_by_owner_with_reason_allowed(
    create_ticket,
    move_ticket,
    agent_be_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")

    response = await move_ticket(agent_be_client, ticket["id"], "BLOCKED", "dependency install failed")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "BLOCKED"


async def test_todo_to_blocked_without_reason_requires_reason(
    create_ticket,
    move_ticket,
    agent_be_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")

    response = await move_ticket(agent_be_client, ticket["id"], "BLOCKED")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "reason_required"


async def test_todo_to_blocked_by_non_owner_agent_returns_403(
    create_ticket,
    move_ticket,
    agent_fe_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")

    response = await move_ticket(agent_fe_client, ticket["id"], "BLOCKED", "dependency install failed")

    assert response.status_code == 403


async def test_in_progress_to_blocked_without_reason_requires_reason(
    create_ticket,
    move_ticket,
    agent_be_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")
    started = await move_ticket(agent_be_client, ticket["id"], "IN_PROGRESS")

    response = await move_ticket(agent_be_client, ticket["id"], "BLOCKED")

    assert started.status_code == 200, started.text
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "reason_required"


async def test_in_progress_to_blocked_with_reason_writes_audit(
    create_ticket,
    move_ticket,
    agent_be_client: httpx.AsyncClient,
    db_fetch_one,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")
    started = await move_ticket(agent_be_client, ticket["id"], "IN_PROGRESS")

    response = await move_ticket(agent_be_client, ticket["id"], "BLOCKED", "waiting on API")
    audit = await db_fetch_one(
        """
        SELECT reason
        FROM ticket_audit_log
        WHERE ticket_id = :ticket_id AND to_status = 'BLOCKED'
        """,
        {"ticket_id": ticket["id"]},
    )

    assert started.status_code == 200, started.text
    assert response.status_code == 200, response.text
    assert audit["reason"] == "waiting on API"


async def test_blocked_to_in_progress_by_owner(
    create_ticket,
    move_ticket,
    agent_be_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")
    await move_ticket(agent_be_client, ticket["id"], "IN_PROGRESS")
    blocked = await move_ticket(agent_be_client, ticket["id"], "BLOCKED", "waiting")

    response = await move_ticket(agent_be_client, ticket["id"], "IN_PROGRESS")

    assert blocked.status_code == 200, blocked.text
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "IN_PROGRESS"


async def test_in_progress_to_in_qa_by_owner(
    create_ticket,
    move_ticket,
    agent_be_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")
    started = await move_ticket(agent_be_client, ticket["id"], "IN_PROGRESS")

    response = await move_ticket(agent_be_client, ticket["id"], "IN_QA")

    assert started.status_code == 200, started.text
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "IN_QA"


async def test_test_only_in_progress_to_done_by_owner(
    create_ticket,
    move_ticket,
    agent_be_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex", ticket_kind="TEST_ONLY")
    started = await move_ticket(agent_be_client, ticket["id"], "IN_PROGRESS")

    response = await move_ticket(agent_be_client, ticket["id"], "DONE")

    assert started.status_code == 200, started.text
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "DONE"


async def test_test_only_in_progress_to_done_by_non_owner_returns_403(
    create_ticket,
    move_ticket,
    agent_fe_client: httpx.AsyncClient,
    agent_be_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex", ticket_kind="TEST_ONLY")
    started = await move_ticket(agent_be_client, ticket["id"], "IN_PROGRESS")

    response = await move_ticket(agent_fe_client, ticket["id"], "DONE")

    assert started.status_code == 200, started.text
    assert response.status_code == 403


async def test_test_only_in_progress_to_in_qa_returns_409(
    create_ticket,
    move_ticket,
    agent_be_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex", ticket_kind="TEST_ONLY")
    started = await move_ticket(agent_be_client, ticket["id"], "IN_PROGRESS")

    response = await move_ticket(agent_be_client, ticket["id"], "IN_QA")

    assert started.status_code == 200, started.text
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_transition"


async def test_test_only_qa_failed_path_returns_409(
    create_ticket,
    move_ticket,
    agent_be_client: httpx.AsyncClient,
    agent_qa_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex", ticket_kind="TEST_ONLY")
    started = await move_ticket(agent_be_client, ticket["id"], "IN_PROGRESS")

    response = await move_ticket(agent_qa_client, ticket["id"], "QA_FAILED", "needs work")

    assert started.status_code == 200, started.text
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_transition"


async def test_in_progress_to_in_qa_fires_review_message(
    create_ticket,
    move_ticket,
    agent_be_client: httpx.AsyncClient,
    db_fetch_all,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")
    started = await move_ticket(agent_be_client, ticket["id"], "IN_PROGRESS")
    response = await move_ticket(agent_be_client, ticket["id"], "IN_QA")
    messages = await db_fetch_all(
        "SELECT type, recipient, sender FROM mailbox_messages WHERE type = 'ticket_review_requested'",
    )
    audit = await db_fetch_all(
        "SELECT from_status, to_status, actor FROM ticket_audit_log WHERE ticket_id = :ticket_id ORDER BY id",
        {"ticket_id": ticket["id"]},
    )

    assert started.status_code == 200, started.text
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "IN_QA"
    assert messages == [
        {"type": "ticket_review_requested", "recipient": "agent:sentinel", "sender": "system:system"}
    ]
    assert {"from_status": "IN_PROGRESS", "to_status": "IN_QA", "actor": "agent:cortex"} in audit


async def test_in_qa_to_in_qa_returns_409(
    create_ticket,
    move_ticket,
    agent_be_client: httpx.AsyncClient,
) -> None:
    ticket = await _in_qa(create_ticket, agent_be_client, move_ticket)

    response = await move_ticket(agent_be_client, ticket["id"], "IN_QA")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_transition"


async def test_in_qa_to_done_by_qa_agent(
    create_ticket,
    move_ticket,
    agent_be_client: httpx.AsyncClient,
    agent_qa_client: httpx.AsyncClient,
    pm_client: httpx.AsyncClient,
) -> None:
    ticket = await _in_qa(create_ticket, agent_be_client, move_ticket)

    response = await move_ticket(agent_qa_client, ticket["id"], "DONE")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "DONE"


async def test_in_qa_to_done_by_non_qa_agent_returns_403(
    create_ticket,
    move_ticket,
    agent_be_client: httpx.AsyncClient,
    pm_client: httpx.AsyncClient,
) -> None:
    ticket = await _in_qa(create_ticket, agent_be_client, move_ticket)

    response = await move_ticket(agent_be_client, ticket["id"], "DONE")

    assert response.status_code == 403


async def test_in_qa_to_qa_failed_by_qa_with_reason(
    create_ticket,
    move_ticket,
    agent_be_client: httpx.AsyncClient,
    agent_qa_client: httpx.AsyncClient,
    pm_client: httpx.AsyncClient,
) -> None:
    ticket = await _in_qa(create_ticket, agent_be_client, move_ticket)

    response = await move_ticket(agent_qa_client, ticket["id"], "QA_FAILED", "needs polish")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "QA_FAILED"


async def test_in_qa_to_qa_failed_without_reason_requires_reason(
    create_ticket,
    move_ticket,
    agent_be_client: httpx.AsyncClient,
    agent_qa_client: httpx.AsyncClient,
    pm_client: httpx.AsyncClient,
) -> None:
    ticket = await _in_qa(create_ticket, agent_be_client, move_ticket)

    response = await move_ticket(agent_qa_client, ticket["id"], "QA_FAILED")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "reason_required"


async def test_qa_failed_to_todo_by_owner(
    create_ticket,
    move_ticket,
    agent_be_client: httpx.AsyncClient,
    agent_qa_client: httpx.AsyncClient,
    pm_client: httpx.AsyncClient,
) -> None:
    ticket = await _in_qa(create_ticket, agent_be_client, move_ticket)
    failed = await move_ticket(agent_qa_client, ticket["id"], "QA_FAILED", "needs polish")

    response = await move_ticket(agent_be_client, ticket["id"], "TODO")

    assert failed.status_code == 200, failed.text
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "TODO"


async def test_any_state_to_cancelled_by_pm_with_override_and_reason(
    create_ticket,
    move_ticket,
    pm_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")

    response = await move_ticket(pm_client, ticket["id"], "CANCELLED", "not needed", True)

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "CANCELLED"


async def test_any_state_to_cancelled_by_pm_without_override_returns_403(
    create_ticket,
    move_ticket,
    pm_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")

    response = await move_ticket(pm_client, ticket["id"], "CANCELLED", "not needed")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "override_not_permitted"


async def test_any_state_to_cancelled_by_agent_returns_403(
    create_ticket,
    move_ticket,
    agent_be_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")

    response = await move_ticket(agent_be_client, ticket["id"], "CANCELLED", "not needed")

    assert response.status_code == 403


async def test_done_is_terminal(
    create_ticket,
    move_ticket,
    agent_be_client: httpx.AsyncClient,
    agent_qa_client: httpx.AsyncClient,
    pm_client: httpx.AsyncClient,
) -> None:
    ticket = await _in_qa(create_ticket, agent_be_client, move_ticket)
    done = await move_ticket(agent_qa_client, ticket["id"], "DONE")

    response = await move_ticket(pm_client, ticket["id"], "TODO", "reopen", True)

    assert done.status_code == 200, done.text
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_transition"


async def test_cancelled_is_terminal(
    create_ticket,
    move_ticket,
    pm_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")
    cancelled = await move_ticket(pm_client, ticket["id"], "CANCELLED", "cancel", True)

    response = await move_ticket(pm_client, ticket["id"], "TODO", "reopen", True)

    assert cancelled.status_code == 200, cancelled.text
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_transition"


async def test_reassignment_by_pm_fires_messages_and_audit(
    create_ticket,
    pm_client: httpx.AsyncClient,
    db_fetch_all,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")

    response = await pm_client.post(
        f"/tickets/{ticket['id']}/assign",
        json={"new_owner_agent_id": "lumen", "reason": "frontend owns this now"},
    )
    audit = await db_fetch_all(
        """
        SELECT from_owner, to_owner
        FROM ticket_audit_log
        WHERE ticket_id = :ticket_id AND from_owner IS NOT NULL
        """,
        {"ticket_id": ticket["id"]},
    )
    messages = await db_fetch_all(
        "SELECT type, recipient FROM mailbox_messages ORDER BY id",
    )

    assert response.status_code == 200, response.text
    assert response.json()["owner_agent_id"] == "lumen"
    assert {"from_owner": "cortex", "to_owner": "lumen"} in audit
    assert {"type": "ticket_unassigned", "recipient": "agent:cortex"} in messages
    assert {"type": "ticket_assigned", "recipient": "agent:lumen"} in messages


async def test_reassignment_to_same_owner_is_noop(
    create_ticket,
    pm_client: httpx.AsyncClient,
    db_fetch_one,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")
    before = await db_fetch_one("SELECT count(*) AS count FROM mailbox_messages")

    response = await pm_client.post(
        f"/tickets/{ticket['id']}/assign",
        json={"new_owner_agent_id": "cortex"},
    )
    after = await db_fetch_one("SELECT count(*) AS count FROM mailbox_messages")

    assert response.status_code == 200, response.text
    assert response.json()["owner_agent_id"] == "cortex"
    assert after["count"] == before["count"]


async def test_assignment_of_unassigned_ticket_fires_only_assigned(
    create_ticket,
    pm_client: httpx.AsyncClient,
    db_fetch_all,
) -> None:
    ticket = await create_ticket(owner_agent_id=None)

    response = await pm_client.post(
        f"/tickets/{ticket['id']}/assign",
        json={"new_owner_agent_id": "cortex"},
    )
    messages = await db_fetch_all("SELECT type, recipient FROM mailbox_messages")

    assert response.status_code == 200, response.text
    assert messages == [{"type": "ticket_assigned", "recipient": "agent:cortex"}]
