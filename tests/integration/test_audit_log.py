"""Integration coverage for append-only ticket audit rows."""

from __future__ import annotations

import httpx
import pytest

from tests.integration.constants import PM_ACTOR

pytestmark = pytest.mark.integration


async def test_creation_writes_one_audit_row(
    create_ticket,
    db_fetch_all,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")

    rows = await db_fetch_all(
        "SELECT from_status, to_status, actor FROM ticket_audit_log WHERE ticket_id = :ticket_id",
        {"ticket_id": ticket["id"]},
    )

    assert rows == [{"from_status": None, "to_status": "TODO", "actor": PM_ACTOR}]


async def test_transition_writes_audit_row_with_reason_and_actor(
    create_ticket,
    move_ticket,
    agent_be_client: httpx.AsyncClient,
    db_fetch_one,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")
    await move_ticket(agent_be_client, ticket["id"], "IN_PROGRESS")

    response = await move_ticket(agent_be_client, ticket["id"], "BLOCKED", "dependency missing")
    audit = await db_fetch_one(
        """
        SELECT from_status, to_status, actor, reason
        FROM ticket_audit_log
        WHERE ticket_id = :ticket_id AND to_status = 'BLOCKED'
        """,
        {"ticket_id": ticket["id"]},
    )

    assert response.status_code == 200, response.text
    assert audit == {
        "from_status": "IN_PROGRESS",
        "to_status": "BLOCKED",
        "actor": "agent:cortex",
        "reason": "dependency missing",
    }


async def test_reassignment_writes_owner_change_audit_row(
    create_ticket,
    pm_client: httpx.AsyncClient,
    db_fetch_one,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")

    response = await pm_client.post(
        f"/tickets/{ticket['id']}/assign",
        json={"new_owner_agent_id": "lumen", "reason": "handoff"},
    )
    audit = await db_fetch_one(
        """
        SELECT from_owner, to_owner, actor, reason
        FROM ticket_audit_log
        WHERE ticket_id = :ticket_id AND from_owner = 'cortex'
        """,
        {"ticket_id": ticket["id"]},
    )

    assert response.status_code == 200, response.text
    assert audit == {
        "from_owner": "cortex",
        "to_owner": "lumen",
        "actor": PM_ACTOR,
        "reason": "handoff",
    }


async def test_pm_override_flag_is_recorded(
    create_ticket,
    move_ticket,
    pm_client: httpx.AsyncClient,
    db_fetch_all,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")

    response = await move_ticket(pm_client, ticket["id"], "CANCELLED", "override cancel", True)
    rows = await db_fetch_all(
        "SELECT to_status, pm_override FROM ticket_audit_log WHERE ticket_id = :ticket_id ORDER BY id",
        {"ticket_id": ticket["id"]},
    )

    assert response.status_code == 200, response.text
    assert rows[0]["pm_override"] is False
    assert rows[-1] == {"to_status": "CANCELLED", "pm_override": True}


async def test_audit_endpoint_returns_rows_in_order(
    create_ticket,
    move_ticket,
    pm_client: httpx.AsyncClient,
    agent_be_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")
    await move_ticket(agent_be_client, ticket["id"], "IN_PROGRESS")
    await move_ticket(pm_client, ticket["id"], "CANCELLED", "done", True)

    response = await pm_client.get(f"/tickets/{ticket['id']}/audit")

    assert response.status_code == 200, response.text
    rows = response.json()
    assert [row["to_status"] for row in rows] == ["TODO", "IN_PROGRESS", "CANCELLED"]
    assert [row["id"] for row in rows] == sorted(row["id"] for row in rows)


async def test_audit_for_nonexistent_ticket_returns_404(
    pm_client: httpx.AsyncClient,
) -> None:
    response = await pm_client.get("/tickets/999999/audit")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ticket_not_found"


async def test_agent_reads_audit_log_for_own_ticket(
    create_ticket,
    agent_be_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")

    response = await agent_be_client.get(f"/tickets/{ticket['id']}/audit")

    assert response.status_code == 200, response.text


async def test_qa_agent_reads_audit_log_for_other_agent_ticket(
    create_ticket,
    agent_qa_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")

    response = await agent_qa_client.get(f"/tickets/{ticket['id']}/audit")

    assert response.status_code == 200, response.text


async def test_agent_reads_audit_log_for_other_ticket(
    create_ticket,
    agent_be_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="lumen")

    response = await agent_be_client.get(f"/tickets/{ticket['id']}/audit")

    assert response.status_code == 200, response.text
