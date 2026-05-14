"""Integration coverage for PM sessions, CSRF, and agent API keys."""

from __future__ import annotations

from time import perf_counter

import httpx
import pytest

from tests.integration.constants import AGENT_KEYS, DEFAULT_REPO, PM_EMAIL, PM_PASSWORD

pytestmark = pytest.mark.integration


async def test_login_with_correct_credentials_sets_session_cookie(
    anonymous_client: httpx.AsyncClient,
) -> None:
    response = await anonymous_client.post(
        "/auth/login",
        json={"email": PM_EMAIL, "password": PM_PASSWORD},
    )

    assert response.status_code == 204, response.text
    assert "crewline_session=" in response.headers["set-cookie"]


async def test_login_with_wrong_password_returns_401_without_cookie(
    anonymous_client: httpx.AsyncClient,
) -> None:
    response = await anonymous_client.post(
        "/auth/login",
        json={"email": PM_EMAIL, "password": "wrong"},
    )

    assert response.status_code == 401
    assert "set-cookie" not in response.headers


async def test_login_with_nonexistent_email_is_constant_timeish(
    anonymous_client: httpx.AsyncClient,
) -> None:
    start = perf_counter()
    wrong_password = await anonymous_client.post(
        "/auth/login",
        json={"email": PM_EMAIL, "password": "wrong"},
    )
    wrong_elapsed = perf_counter() - start

    start = perf_counter()
    missing_user = await anonymous_client.post(
        "/auth/login",
        json={"email": "nobody@crewline.local", "password": "wrong"},
    )
    missing_elapsed = perf_counter() - start

    assert wrong_password.status_code == 401
    assert missing_user.status_code == 401
    assert abs(wrong_elapsed - missing_elapsed) < 1.0


async def test_auth_me_with_valid_cookie_returns_identity_and_csrf(
    pm_client: httpx.AsyncClient,
) -> None:
    response = await pm_client.get("/auth/me")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["email"] == PM_EMAIL
    assert body["display_name"] == "PM"
    assert body["user_id"] == "00000000-0000-0000-0000-000000000001"
    assert body["csrf_token"]


async def test_auth_me_without_cookie_returns_401(
    anonymous_client: httpx.AsyncClient,
) -> None:
    response = await anonymous_client.get("/auth/me")

    assert response.status_code == 401


async def test_auth_me_with_malformed_cookie_returns_401(
    anonymous_client: httpx.AsyncClient,
) -> None:
    anonymous_client.cookies.set("crewline_session", "not-a-real-session")

    response = await anonymous_client.get("/auth/me")

    assert response.status_code == 401


async def test_logout_invalidates_session(pm_client: httpx.AsyncClient) -> None:
    logout = await pm_client.post("/auth/logout")
    after_logout = await pm_client.get("/auth/me")

    assert logout.status_code == 204, logout.text
    assert after_logout.status_code == 401


async def test_mutating_request_without_csrf_returns_csrf_invalid(
    pm_client_no_csrf: httpx.AsyncClient,
) -> None:
    response = await pm_client_no_csrf.post(
        "/tickets",
        json={"title": "needs csrf", "repo_full_name": DEFAULT_REPO},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_invalid"


async def test_mutating_request_with_wrong_csrf_returns_csrf_invalid(
    pm_client_no_csrf: httpx.AsyncClient,
) -> None:
    pm_client_no_csrf.headers["X-CSRF-Token"] = "wrong-token"

    response = await pm_client_no_csrf.post(
        "/tickets",
        json={"title": "bad csrf", "repo_full_name": DEFAULT_REPO},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_invalid"


async def test_get_request_without_csrf_succeeds(
    pm_client_no_csrf: httpx.AsyncClient,
) -> None:
    response = await pm_client_no_csrf.get("/tickets")

    assert response.status_code == 200, response.text


async def test_valid_agent_api_key_authenticates(
    agent_be_client: httpx.AsyncClient,
    db_fetch_one,
) -> None:
    response = await agent_be_client.get("/agents")
    credential = await db_fetch_one(
        "SELECT last_used_at FROM agent_credentials WHERE agent_id = :agent_id",
        {"agent_id": "be"},
    )

    assert response.status_code == 200, response.text
    assert credential["last_used_at"] is not None


async def test_invalid_agent_api_key_returns_401(
    anonymous_client: httpx.AsyncClient,
) -> None:
    response = await anonymous_client.get(
        "/agents",
        headers={"Authorization": "Bearer wrong-key"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_api_key"


async def test_revoked_agent_api_key_returns_401(
    anonymous_client: httpx.AsyncClient,
    db_execute,
) -> None:
    await db_execute(
        "UPDATE agent_credentials SET revoked_at = now() WHERE agent_id = :agent_id",
        {"agent_id": "be"},
    )

    response = await anonymous_client.get(
        "/agents",
        headers={"Authorization": f"Bearer {AGENT_KEYS['be']}"},
    )

    assert response.status_code == 401


async def test_agent_mutation_does_not_require_csrf(
    create_ticket,
    agent_be_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(title="agent csrf", owner_agent_id="be")

    response = await agent_be_client.post(
        f"/tickets/{ticket['id']}/transitions",
        json={"to_status": "IN_PROGRESS"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "IN_PROGRESS"


@pytest.mark.parametrize("path", ["/healthz", "/openapi.json"])
async def test_public_paths_do_not_require_auth(
    anonymous_client: httpx.AsyncClient,
    path: str,
) -> None:
    response = await anonymous_client.get(path)

    assert response.status_code == 200, response.text


async def test_session_expiry_returns_401(
    pm_client_no_csrf: httpx.AsyncClient,
    db_execute,
) -> None:
    await db_execute("UPDATE sessions SET last_seen_at = now() - interval '25 hours'")

    response = await pm_client_no_csrf.get("/auth/me")

    assert response.status_code == 401
