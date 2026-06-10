"""Integration coverage for authz rules around ticket ownership and PM powers."""

from __future__ import annotations

import httpx
import pytest

pytestmark = pytest.mark.integration


async def test_agent_reads_own_ticket(
    create_ticket,
    agent_be_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")

    response = await agent_be_client.get(f"/tickets/{ticket['id']}")

    assert response.status_code == 200, response.text


async def test_qa_agent_reads_ticket_owned_by_implementation_agent(
    create_ticket,
    agent_qa_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")

    response = await agent_qa_client.get(f"/tickets/{ticket['id']}")

    assert response.status_code == 200, response.text
    assert response.json()["id"] == ticket["id"]
    assert response.json()["owner_agent_id"] == "cortex"


async def test_agent_transitions_own_ticket(
    create_ticket,
    move_ticket,
    agent_be_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")

    response = await move_ticket(agent_be_client, ticket["id"], "IN_PROGRESS")

    assert response.status_code == 200, response.text


async def test_agent_transitions_other_ticket_returns_403(
    create_ticket,
    move_ticket,
    agent_be_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="lumen")

    response = await move_ticket(agent_be_client, ticket["id"], "IN_PROGRESS")

    assert response.status_code == 403


async def test_agent_adds_artifact_to_own_ticket(
    create_ticket,
    agent_be_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")

    response = await agent_be_client.post(
        f"/tickets/{ticket['id']}/artifacts",
        json={"artifact_type": "note", "content": "owned"},
    )

    assert response.status_code == 201, response.text


async def test_agent_adds_artifact_to_other_ticket_returns_403(
    create_ticket,
    agent_be_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="lumen")

    response = await agent_be_client.post(
        f"/tickets/{ticket['id']}/artifacts",
        json={"artifact_type": "note", "content": "not owned"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "actor_not_permitted"


async def test_pm_accesses_ticket_child_resources(
    create_ticket,
    pm_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")
    artifact = await pm_client.post(
        f"/tickets/{ticket['id']}/artifacts",
        json={"artifact_type": "pm_note", "content": "pm"},
    )

    ticket_read = await pm_client.get(f"/tickets/{ticket['id']}")
    audit = await pm_client.get(f"/tickets/{ticket['id']}/audit")
    artifacts = await pm_client.get(f"/tickets/{ticket['id']}/artifacts")
    metrics = await pm_client.get(f"/tickets/{ticket['id']}/metrics")

    assert artifact.status_code == 201, artifact.text
    assert ticket_read.status_code == 200, ticket_read.text
    assert audit.status_code == 200, audit.text
    assert artifacts.status_code == 200, artifacts.text
    assert metrics.status_code == 200, metrics.text


async def test_agent_list_includes_own_only(
    create_ticket,
    agent_be_client: httpx.AsyncClient,
) -> None:
    own = await create_ticket(owner_agent_id="cortex")
    other = await create_ticket(owner_agent_id="lumen")

    response = await agent_be_client.get("/tickets")

    assert response.status_code == 200, response.text
    ids = {item["id"] for item in response.json()["items"]}
    assert ids == {own["id"]}
    assert other["id"] not in ids


async def test_pm_list_filter_sees_all_matching_tickets(
    create_ticket,
    pm_client: httpx.AsyncClient,
) -> None:
    first = await create_ticket(owner_agent_id="cortex")
    second = await create_ticket(owner_agent_id="lumen")

    response = await pm_client.get("/tickets")

    assert response.status_code == 200, response.text
    ids = {item["id"] for item in response.json()["items"]}
    assert {first["id"], second["id"]}.issubset(ids)
