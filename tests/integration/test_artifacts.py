"""Integration coverage for immutable ticket artifacts."""

from __future__ import annotations

import httpx
import pytest

from tests.integration.constants import PM_ACTOR

pytestmark = pytest.mark.integration


async def test_agent_adds_artifact_to_own_ticket(
    create_ticket,
    agent_be_client: httpx.AsyncClient,
    db_fetch_one,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")

    response = await agent_be_client.post(
        f"/tickets/{ticket['id']}/artifacts",
        json={"artifact_type": "note", "content": "implementation note"},
    )
    row = await db_fetch_one(
        "SELECT author FROM ticket_artifacts WHERE id = :artifact_id",
        {"artifact_id": response.json()["id"] if response.status_code == 201 else -1},
    )

    assert response.status_code == 201, response.text
    assert response.json()["author"] == "agent:cortex"
    assert row["author"] == "agent:cortex"


async def test_agent_adds_artifact_to_other_ticket_returns_403(
    create_ticket,
    agent_be_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="lumen")

    response = await agent_be_client.post(
        f"/tickets/{ticket['id']}/artifacts",
        json={"artifact_type": "note", "content": "blocked"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "actor_not_permitted"


async def test_qa_agent_adds_artifact_to_other_agent_ticket(
    create_ticket,
    agent_qa_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")

    response = await agent_qa_client.post(
        f"/tickets/{ticket['id']}/artifacts",
        json={"artifact_type": "qa_review", "content": "review note"},
    )

    assert response.status_code == 201, response.text
    assert response.json()["author"] == "agent:sentinel"


async def test_pm_adds_artifact(
    create_ticket,
    pm_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")

    response = await pm_client.post(
        f"/tickets/{ticket['id']}/artifacts",
        json={"artifact_type": "pm_note", "content": "looks good"},
    )

    assert response.status_code == 201, response.text
    assert response.json()["author"] == PM_ACTOR


async def test_list_artifacts_on_ticket_returns_in_order(
    create_ticket,
    pm_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")
    first = await pm_client.post(
        f"/tickets/{ticket['id']}/artifacts",
        json={"artifact_type": "note", "content": "order 1"},
    )
    second = await pm_client.post(
        f"/tickets/{ticket['id']}/artifacts",
        json={"artifact_type": "note", "content": "order 2"},
    )

    response = await pm_client.get(f"/tickets/{ticket['id']}/artifacts")

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert response.status_code == 200, response.text
    assert [item["id"] for item in response.json()] == [first.json()["id"], second.json()["id"]]


async def test_qa_agent_lists_artifacts_for_other_agent_ticket(
    create_ticket,
    pm_client: httpx.AsyncClient,
    agent_qa_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")
    artifact = await pm_client.post(
        f"/tickets/{ticket['id']}/artifacts",
        json={"artifact_type": "implementation", "content": "ready for review"},
    )

    response = await agent_qa_client.get(f"/tickets/{ticket['id']}/artifacts")

    assert artifact.status_code == 201, artifact.text
    assert response.status_code == 200, response.text
    assert [item["id"] for item in response.json()] == [artifact.json()["id"]]


async def test_adding_artifact_to_nonexistent_ticket_returns_404(
    pm_client: httpx.AsyncClient,
) -> None:
    response = await pm_client.post(
        "/tickets/999999/artifacts",
        json={"artifact_type": "note", "content": "missing"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ticket_not_found"


async def test_artifact_create_rejects_extra_fields(
    create_ticket,
    pm_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")

    response = await pm_client.post(
        f"/tickets/{ticket['id']}/artifacts",
        json={
            "artifact_type": "note",
            "content": "extra",
            "author": "agent:cortex",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
