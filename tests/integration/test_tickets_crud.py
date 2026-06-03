"""Integration coverage for ticket CRUD and list behavior."""

from __future__ import annotations

import httpx
import pytest

from tests.integration.constants import DEFAULT_REPO

pytestmark = pytest.mark.integration


async def test_pm_creates_ticket_with_owner(
    pm_client: httpx.AsyncClient,
    db_fetch_one,
) -> None:
    response = await pm_client.post(
        "/tickets",
        json={"title": "owned ticket", "owner_agent_id": "cortex", "repo_full_name": DEFAULT_REPO},
    )

    assert response.status_code == 201, response.text
    ticket = response.json()
    assert ticket["status"] == "TODO"
    assert ticket["owner_agent_id"] == "cortex"

    row = await db_fetch_one(
        "SELECT status, owner_agent_id, repo_full_name FROM tickets WHERE id = :ticket_id",
        {"ticket_id": ticket["id"]},
    )
    audit = await db_fetch_one(
        "SELECT to_status, to_owner FROM ticket_audit_log WHERE ticket_id = :ticket_id",
        {"ticket_id": ticket["id"]},
    )
    mailbox = await db_fetch_one(
        "SELECT type, recipient FROM mailbox_messages WHERE payload->>'ticket_id' = :ticket_id",
        {"ticket_id": str(ticket["id"])},
    )

    assert row == {
        "status": "TODO",
        "owner_agent_id": "cortex",
        "repo_full_name": DEFAULT_REPO,
    }
    assert audit == {"to_status": "TODO", "to_owner": "cortex"}
    assert mailbox == {"type": "ticket_assigned", "recipient": "agent:cortex"}


async def test_pm_creates_ticket_without_owner(
    pm_client: httpx.AsyncClient,
    db_fetch_one,
) -> None:
    response = await pm_client.post(
        "/tickets",
        json={"title": "unowned ticket", "repo_full_name": DEFAULT_REPO},
    )

    assert response.status_code == 201, response.text
    ticket = response.json()
    mailbox = await db_fetch_one("SELECT count(*) AS count FROM mailbox_messages")

    assert ticket["status"] == "TODO"
    assert ticket["owner_agent_id"] is None
    assert mailbox["count"] == 0


async def test_pm_creates_with_invalid_agent_id(pm_client: httpx.AsyncClient) -> None:
    response = await pm_client.post(
        "/tickets",
        json={"title": "bad owner", "owner_agent_id": "missing", "repo_full_name": DEFAULT_REPO},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "agent_not_found"


async def test_agent_cannot_create_tickets(agent_be_client: httpx.AsyncClient) -> None:
    response = await agent_be_client.post(
        "/tickets",
        json={"title": "agent create", "repo_full_name": DEFAULT_REPO},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "actor_not_permitted"


async def test_list_tickets_empty(pm_client: httpx.AsyncClient) -> None:
    response = await pm_client.get("/tickets")

    assert response.status_code == 200, response.text
    assert response.json() == {"items": [], "limit": 50, "offset": 0, "has_more": False}


async def test_list_tickets_pagination(
    create_ticket,
    pm_client: httpx.AsyncClient,
) -> None:
    for index in range(5):
        await create_ticket(title=f"page {index}", owner_agent_id="cortex")

    response = await pm_client.get("/tickets", params={"limit": 2, "offset": 0})

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["items"]) == 2
    assert body["limit"] == 2
    assert body["offset"] == 0
    assert body["has_more"] is True


async def test_list_tickets_status_filter(
    create_ticket,
    move_ticket,
    pm_client: httpx.AsyncClient,
    agent_be_client: httpx.AsyncClient,
) -> None:
    todo = await create_ticket(title="todo", owner_agent_id="cortex")
    in_progress = await create_ticket(title="in progress", owner_agent_id="cortex")
    moved = await move_ticket(agent_be_client, in_progress["id"], "IN_PROGRESS")

    response = await pm_client.get("/tickets", params={"status": "IN_PROGRESS"})

    assert moved.status_code == 200, moved.text
    assert response.status_code == 200, response.text
    ids = {item["id"] for item in response.json()["items"]}
    assert ids == {in_progress["id"]}
    assert todo["id"] not in ids


async def test_list_tickets_owner_filter(
    create_ticket,
    pm_client: httpx.AsyncClient,
) -> None:
    be_ticket = await create_ticket(title="cortex ticket", owner_agent_id="cortex")
    fe_ticket = await create_ticket(title="lumen ticket", owner_agent_id="lumen")

    response = await pm_client.get("/tickets", params={"owner_agent_id": "lumen"})

    assert response.status_code == 200, response.text
    ids = {item["id"] for item in response.json()["items"]}
    assert ids == {fe_ticket["id"]}
    assert be_ticket["id"] not in ids


async def test_agent_sees_only_own_tickets_in_list(
    create_ticket,
    agent_be_client: httpx.AsyncClient,
) -> None:
    own = await create_ticket(title="own", owner_agent_id="cortex")
    other = await create_ticket(title="other", owner_agent_id="lumen")

    response = await agent_be_client.get("/tickets")

    assert response.status_code == 200, response.text
    ids = {item["id"] for item in response.json()["items"]}
    assert ids == {own["id"]}
    assert other["id"] not in ids


async def test_pm_updates_ticket_title_without_audit_row(
    create_ticket,
    pm_client: httpx.AsyncClient,
    db_fetch_one,
) -> None:
    ticket = await create_ticket(title="before", owner_agent_id="cortex")
    before = await db_fetch_one(
        "SELECT count(*) AS count FROM ticket_audit_log WHERE ticket_id = :ticket_id",
        {"ticket_id": ticket["id"]},
    )

    response = await pm_client.patch(f"/tickets/{ticket['id']}", json={"title": "after"})
    after = await db_fetch_one(
        "SELECT count(*) AS count FROM ticket_audit_log WHERE ticket_id = :ticket_id",
        {"ticket_id": ticket["id"]},
    )

    assert response.status_code == 200, response.text
    assert response.json()["title"] == "after"
    assert after["count"] == before["count"]


async def test_pm_updates_with_extra_fields_returns_422(
    create_ticket,
    pm_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(title="strict", owner_agent_id="cortex")

    response = await pm_client.patch(
        f"/tickets/{ticket['id']}",
        json={"title": "after", "status": "DONE"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_agent_cannot_update_ticket_fields(
    create_ticket,
    agent_be_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(title="immutable by agent", owner_agent_id="cortex")

    response = await agent_be_client.patch(
        f"/tickets/{ticket['id']}",
        json={"title": "agent edit"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "actor_not_permitted"


async def test_get_nonexistent_ticket_returns_404(pm_client: httpx.AsyncClient) -> None:
    response = await pm_client.get("/tickets/999999")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ticket_not_found"


async def test_agent_gets_own_ticket(
    create_ticket,
    agent_be_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(title="own read", owner_agent_id="cortex")

    response = await agent_be_client.get(f"/tickets/{ticket['id']}")

    assert response.status_code == 200, response.text
    assert response.json()["id"] == ticket["id"]


async def test_agent_gets_other_agents_ticket(
    create_ticket,
    agent_be_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(title="other read", owner_agent_id="lumen")

    response = await agent_be_client.get(f"/tickets/{ticket['id']}")

    assert response.status_code == 200, response.text
    assert response.json()["id"] == ticket["id"]
