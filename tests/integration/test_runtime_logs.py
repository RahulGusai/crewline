"""Integration coverage for runtime activity logs and cost summaries."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

pytestmark = pytest.mark.integration


def _runtime_log_payload(ticket_id: int, agent_id: str = "cortex", model: str | None = "claude-sonnet-4-6") -> dict:
    return {
        "ticket_id": ticket_id,
        "agent_id": agent_id,
        "runtime_type": "ticket_work",
        "started_at": datetime(2026, 5, 14, 10, 0, tzinfo=UTC).isoformat(),
        "ended_at": datetime(2026, 5, 14, 10, 5, tzinfo=UTC).isoformat(),
        "outcome": "completed",
        "total_turns": 4,
        "model": model,
        "input_tokens": 1_000_000,
        "output_tokens": 1_000_000,
        "classification": None,
        "content": "# Runtime log\n\nCompleted work.",
    }


async def test_create_list_and_fetch_runtime_log(
    create_ticket,
    agent_be_client: httpx.AsyncClient,
    pm_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")

    created = await agent_be_client.post(
        f"/tickets/{ticket['id']}/runtime-logs",
        json=_runtime_log_payload(ticket["id"]),
    )
    listed = await pm_client.get(f"/tickets/{ticket['id']}/runtime-logs")
    detail = await pm_client.get(f"/runtime-logs/{created.json()['id']}")

    assert created.status_code == 201, created.text
    assert listed.status_code == 200, listed.text
    assert listed.json()[0]["id"] == created.json()["id"]
    assert "content" not in listed.json()[0]
    assert detail.status_code == 200, detail.text
    assert detail.json()["content"].startswith("# Runtime log")


async def test_qa_agent_can_read_runtime_logs_for_non_owned_ticket(
    create_ticket,
    agent_be_client: httpx.AsyncClient,
    agent_qa_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")
    created = await agent_be_client.post(
        f"/tickets/{ticket['id']}/runtime-logs",
        json=_runtime_log_payload(ticket["id"]),
    )

    listed = await agent_qa_client.get(f"/tickets/{ticket['id']}/runtime-logs")
    cost = await agent_qa_client.get(f"/tickets/{ticket['id']}/cost")
    detail = await agent_qa_client.get(f"/runtime-logs/{created.json()['id']}")

    assert created.status_code == 201, created.text
    assert listed.status_code == 200, listed.text
    assert listed.json()[0]["id"] == created.json()["id"]
    assert cost.status_code == 200, cost.text
    assert cost.json()["ticket_id"] == ticket["id"]
    assert detail.status_code == 200, detail.text
    assert detail.json()["content"].startswith("# Runtime log")


async def test_non_owner_non_qa_agent_can_read_runtime_logs(
    create_ticket,
    agent_be_client: httpx.AsyncClient,
    agent_fe_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")
    created = await agent_be_client.post(
        f"/tickets/{ticket['id']}/runtime-logs",
        json=_runtime_log_payload(ticket["id"]),
    )

    listed = await agent_fe_client.get(f"/tickets/{ticket['id']}/runtime-logs")
    cost = await agent_fe_client.get(f"/tickets/{ticket['id']}/cost")
    detail = await agent_fe_client.get(f"/runtime-logs/{created.json()['id']}")

    assert created.status_code == 201, created.text
    assert listed.status_code == 200, listed.text
    assert cost.status_code == 200, cost.text
    assert detail.status_code == 200, detail.text


async def test_runtime_log_filter_and_classification(
    create_ticket,
    agent_be_client: httpx.AsyncClient,
    pm_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")
    payload = _runtime_log_payload(ticket["id"])
    payload["outcome"] = "failed"
    payload["classification"] = "dependency_error"

    created = await agent_be_client.post(f"/tickets/{ticket['id']}/runtime-logs", json=payload)
    response = await pm_client.get(f"/tickets/{ticket['id']}/runtime-logs", params={"agent_id": "cortex"})

    assert created.status_code == 201, created.text
    assert response.status_code == 200, response.text
    assert response.json()[0]["classification"] == "dependency_error"


async def test_runtime_log_agent_identity_must_match_body(
    create_ticket,
    agent_be_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")
    payload = _runtime_log_payload(ticket["id"], agent_id="lumen")

    response = await agent_be_client.post(f"/tickets/{ticket['id']}/runtime-logs", json=payload)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "actor_not_permitted"


async def test_runtime_log_path_body_ticket_mismatch(
    create_ticket,
    agent_be_client: httpx.AsyncClient,
) -> None:
    first = await create_ticket(title="first", owner_agent_id="cortex")
    second = await create_ticket(title="second", owner_agent_id="cortex")

    response = await agent_be_client.post(
        f"/tickets/{first['id']}/runtime-logs",
        json=_runtime_log_payload(second["id"]),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "runtime_log_ticket_mismatch"


async def test_runtime_log_costs_are_computed(
    create_ticket,
    agent_be_client: httpx.AsyncClient,
    pm_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")
    known = await agent_be_client.post(
        f"/tickets/{ticket['id']}/runtime-logs",
        json=_runtime_log_payload(ticket["id"], model="claude-sonnet-4-6"),
    )
    unknown_payload = _runtime_log_payload(ticket["id"], model="unknown-model")
    unknown_payload["content"] = "unknown model"
    unknown = await agent_be_client.post(f"/tickets/{ticket['id']}/runtime-logs", json=unknown_payload)

    logs = await pm_client.get(f"/tickets/{ticket['id']}/runtime-logs")
    cost = await pm_client.get(f"/tickets/{ticket['id']}/cost")

    assert known.status_code == 201, known.text
    assert unknown.status_code == 201, unknown.text
    assert logs.status_code == 200, logs.text
    assert [item["cost_usd"] for item in logs.json()] == [18.0, None]
    assert cost.status_code == 200, cost.text
    assert cost.json()["runtime_count"] == 2
    assert cost.json()["total_cost_usd"] == 18.0
