"""Integration coverage for GitHub App management and ticket GitHub endpoints."""

from __future__ import annotations

import httpx
import pytest
import respx

from app.integrations.github import GITHUB_API
from tests.integration.constants import DEFAULT_REPO, OTHER_REPO, RELATED_REPO

pytestmark = pytest.mark.integration


def _mock_installation_token(token: str = "ghs_test_token") -> None:
    respx.post(f"{GITHUB_API}/app/installations/123/access_tokens").mock(
        return_value=httpx.Response(
            201,
            json={"token": token, "expires_at": "2026-05-14T11:00:00Z"},
        )
    )


def _mock_default_installation() -> None:
    respx.get(f"{GITHUB_API}/app/installations/123").mock(
        return_value=httpx.Response(
            200,
            json={"account": {"login": "octo-org", "type": "Organization"}},
        )
    )
    _mock_installation_token()
    respx.get(f"{GITHUB_API}/installation/repositories").mock(
        return_value=httpx.Response(
            200,
            json={
                "repositories": [
                    {"id": 444, "full_name": "octo-org/backend", "default_branch": "main"},
                    {"id": 555, "full_name": "octo-org/frontend", "default_branch": "trunk"},
                ]
            },
        )
    )


async def test_github_install_redirect_creates_state(pm_client: httpx.AsyncClient) -> None:
    response = await pm_client.get("/github/install", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"].startswith("https://github.com/apps/Crewline/installations/new")
    assert "state=" in response.headers["location"]


@respx.mock
async def test_github_callback_connects_installation(
    pm_client: httpx.AsyncClient,
) -> None:
    install = await pm_client.get("/github/install", follow_redirects=False)
    state = install.headers["location"].split("state=", 1)[1]
    _mock_default_installation()

    callback = await pm_client.get(
        "/github/callback",
        params={"installation_id": 123, "setup_action": "install", "state": state},
        follow_redirects=False,
    )
    repos = await pm_client.get("/github/repos")

    assert callback.status_code == 307
    assert repos.status_code == 200, repos.text
    assert [repo["full_name"] for repo in repos.json()] == [
        "octo-org/backend",
        "octo-org/frontend",
    ]


async def test_github_repos_returns_seeded_installation(pm_client: httpx.AsyncClient) -> None:
    response = await pm_client.get("/github/repos")

    assert response.status_code == 200, response.text
    assert {repo["full_name"] for repo in response.json()} == {
        DEFAULT_REPO,
        RELATED_REPO,
        OTHER_REPO,
    }


@respx.mock
async def test_github_refresh_replaces_repos(pm_client: httpx.AsyncClient) -> None:
    respx.post(f"{GITHUB_API}/app/installations/98765/access_tokens").mock(
        return_value=httpx.Response(
            201,
            json={"token": "ghs_refresh", "expires_at": "2026-05-14T11:00:00Z"},
        )
    )
    respx.get(f"{GITHUB_API}/installation/repositories").mock(
        return_value=httpx.Response(
            200,
            json={"repositories": [{"id": 999, "full_name": "acme/new", "default_branch": "main"}]},
        )
    )

    response = await pm_client.post("/github/refresh-repos")

    assert response.status_code == 200, response.text
    assert response.json() == [{"id": 999, "full_name": "acme/new", "default_branch": "main"}]


async def test_github_disconnect_revokes_installation(pm_client: httpx.AsyncClient) -> None:
    disconnect = await pm_client.post("/github/disconnect")
    repos = await pm_client.get("/github/repos")

    assert disconnect.status_code == 204, disconnect.text
    assert repos.status_code == 400
    assert repos.json()["error"]["code"] == "github_not_connected"


@respx.mock
async def test_agent_mints_repo_scoped_github_token(
    create_ticket,
    agent_be_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")
    respx.post(f"{GITHUB_API}/app/installations/98765/access_tokens").mock(
        return_value=httpx.Response(
            201,
            json={"token": "ghs_ticket", "expires_at": "2026-05-14T11:00:00Z"},
        )
    )

    response = await agent_be_client.post(f"/tickets/{ticket['id']}/github-token")

    assert response.status_code == 200, response.text
    assert response.json()["token"] == "ghs_ticket"
    assert response.json()["repo_full_name"] == DEFAULT_REPO
    assert "ghs_ticket" in response.json()["clone_url"]


@respx.mock
async def test_agent_mints_repo_scoped_github_token_for_other_agents_ticket(
    create_ticket,
    agent_fe_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")
    respx.post(f"{GITHUB_API}/app/installations/98765/access_tokens").mock(
        return_value=httpx.Response(
            201,
            json={"token": "ghs_question_ticket", "expires_at": "2026-05-14T11:00:00Z"},
        )
    )

    response = await agent_fe_client.post(f"/tickets/{ticket['id']}/github-token")

    assert response.status_code == 200, response.text
    assert response.json()["token"] == "ghs_question_ticket"
    assert response.json()["repo_full_name"] == DEFAULT_REPO


@respx.mock
async def test_qa_agent_mints_repo_scoped_github_token_for_review(
    create_ticket,
    agent_qa_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")
    respx.post(f"{GITHUB_API}/app/installations/98765/access_tokens").mock(
        return_value=httpx.Response(
            201,
            json={"token": "ghs_qa_ticket", "expires_at": "2026-05-14T11:00:00Z"},
        )
    )

    response = await agent_qa_client.post(f"/tickets/{ticket['id']}/github-token")

    assert response.status_code == 200, response.text
    assert response.json()["token"] == "ghs_qa_ticket"
    assert response.json()["repo_full_name"] == DEFAULT_REPO


@respx.mock
async def test_agent_mints_related_repo_token(
    create_ticket,
    agent_be_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex", related_repo_full_names=[RELATED_REPO])
    respx.post(f"{GITHUB_API}/app/installations/98765/access_tokens").mock(
        return_value=httpx.Response(
            201,
            json={"token": "ghs_related", "expires_at": "2026-05-14T11:00:00Z"},
        )
    )

    response = await agent_be_client.post(
        f"/tickets/{ticket['id']}/github-token",
        json={"repo_full_name": RELATED_REPO},
    )

    assert response.status_code == 200, response.text
    assert response.json()["repo_full_name"] == RELATED_REPO


async def test_agent_cannot_mint_token_for_unrelated_repo(
    create_ticket,
    agent_be_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")

    response = await agent_be_client.post(
        f"/tickets/{ticket['id']}/github-token",
        json={"repo_full_name": RELATED_REPO},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "repo_not_accessible"


async def test_ticket_creation_requires_connected_github(
    pm_client: httpx.AsyncClient,
    db_execute,
) -> None:
    await db_execute("DELETE FROM github_installations")

    response = await pm_client.post(
        "/tickets",
        json={"title": "no github", "repo_full_name": DEFAULT_REPO},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "github_not_connected"


async def test_ticket_creation_rejects_invalid_repo(pm_client: httpx.AsyncClient) -> None:
    response = await pm_client.post(
        "/tickets",
        json={"title": "bad repo", "repo_full_name": "missing/repo"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "repo_not_accessible"


async def test_ticket_creation_and_update_related_repos(
    pm_client: httpx.AsyncClient,
) -> None:
    created = await pm_client.post(
        "/tickets",
        json={
            "title": "with related",
            "repo_full_name": DEFAULT_REPO,
            "related_repo_full_names": [RELATED_REPO],
        },
    )
    updated = await pm_client.patch(
        f"/tickets/{created.json()['id']}",
        json={"related_repo_full_names": [OTHER_REPO]},
    )

    assert created.status_code == 201, created.text
    assert created.json()["related_repo_full_names"] == [RELATED_REPO]
    assert updated.status_code == 200, updated.text
    assert updated.json()["related_repo_full_names"] == [OTHER_REPO]


async def test_ticket_creation_rejects_invalid_related_repo(pm_client: httpx.AsyncClient) -> None:
    response = await pm_client.post(
        "/tickets",
        json={
            "title": "bad related",
            "repo_full_name": DEFAULT_REPO,
            "related_repo_full_names": [DEFAULT_REPO],
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "related_repo_invalid"


async def test_set_pr_url_validates_owner_format_repo_and_single_write(
    create_ticket,
    agent_be_client: httpx.AsyncClient,
    agent_fe_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")
    non_owner = await agent_fe_client.post(
        f"/tickets/{ticket['id']}/pr-url",
        json={"pr_url": f"https://github.com/{DEFAULT_REPO}/pull/1"},
    )
    malformed = await agent_be_client.post(
        f"/tickets/{ticket['id']}/pr-url",
        json={"pr_url": "not-a-github-pr"},
    )
    mismatch = await agent_be_client.post(
        f"/tickets/{ticket['id']}/pr-url",
        json={"pr_url": "https://github.com/acme/other/pull/1"},
    )
    valid = await agent_be_client.post(
        f"/tickets/{ticket['id']}/pr-url",
        json={"pr_url": f"https://github.com/{DEFAULT_REPO}/pull/42"},
    )
    duplicate = await agent_be_client.post(
        f"/tickets/{ticket['id']}/pr-url",
        json={"pr_url": f"https://github.com/{DEFAULT_REPO}/pull/43"},
    )

    assert non_owner.status_code == 403
    assert malformed.status_code == 422
    assert malformed.json()["error"]["code"] == "invalid_pr_url_format"
    assert mismatch.status_code == 422
    assert mismatch.json()["error"]["code"] == "pr_url_repo_mismatch"
    assert valid.status_code == 200, valid.text
    assert valid.json()["pr_url"] == f"https://github.com/{DEFAULT_REPO}/pull/42"
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "pr_url_already_set"


@respx.mock
async def test_merge_pr_happy_path(
    create_ticket,
    move_ticket,
    agent_be_client: httpx.AsyncClient,
    agent_qa_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")
    await agent_be_client.post(
        f"/tickets/{ticket['id']}/pr-url",
        json={"pr_url": f"https://github.com/{DEFAULT_REPO}/pull/42"},
    )
    await move_ticket(agent_be_client, ticket["id"], "IN_PROGRESS")
    await move_ticket(agent_be_client, ticket["id"], "IN_QA")
    done = await move_ticket(agent_qa_client, ticket["id"], "DONE")
    respx.post(f"{GITHUB_API}/app/installations/98765/access_tokens").mock(
        return_value=httpx.Response(
            201,
            json={"token": "ghs_merge", "expires_at": "2026-05-14T11:00:00Z"},
        )
    )
    respx.put(f"{GITHUB_API}/repos/{DEFAULT_REPO}/pulls/42/merge").mock(
        return_value=httpx.Response(200, json={"sha": "abc123", "message": "Merged"})
    )

    response = await agent_be_client.post(f"/tickets/{ticket['id']}/merge-pr")

    assert done.status_code == 200, done.text
    assert response.status_code == 200, response.text
    assert response.json() == {
        "merged": True,
        "sha": "abc123",
        "message": "Merged",
        "error_code": None,
        "error_message": None,
    }


@respx.mock
async def test_qa_agent_can_merge_pr_after_done(
    create_ticket,
    move_ticket,
    agent_be_client: httpx.AsyncClient,
    agent_qa_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")
    await agent_be_client.post(
        f"/tickets/{ticket['id']}/pr-url",
        json={"pr_url": f"https://github.com/{DEFAULT_REPO}/pull/42"},
    )
    await move_ticket(agent_be_client, ticket["id"], "IN_PROGRESS")
    await move_ticket(agent_be_client, ticket["id"], "IN_QA")
    done = await move_ticket(agent_qa_client, ticket["id"], "DONE")
    respx.post(f"{GITHUB_API}/app/installations/98765/access_tokens").mock(
        return_value=httpx.Response(
            201,
            json={"token": "ghs_merge", "expires_at": "2026-05-14T11:00:00Z"},
        )
    )
    respx.put(f"{GITHUB_API}/repos/{DEFAULT_REPO}/pulls/42/merge").mock(
        return_value=httpx.Response(200, json={"sha": "def456", "message": "Merged by QA"})
    )

    response = await agent_qa_client.post(f"/tickets/{ticket['id']}/merge-pr")

    assert done.status_code == 200, done.text
    assert response.status_code == 200, response.text
    assert response.json()["merged"] is True
    assert response.json()["sha"] == "def456"


async def test_merge_pr_requires_pr_url_and_done(
    create_ticket,
    agent_be_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")

    no_pr = await agent_be_client.post(f"/tickets/{ticket['id']}/merge-pr")
    await agent_be_client.post(
        f"/tickets/{ticket['id']}/pr-url",
        json={"pr_url": f"https://github.com/{DEFAULT_REPO}/pull/42"},
    )
    not_done = await agent_be_client.post(f"/tickets/{ticket['id']}/merge-pr")

    assert no_pr.status_code == 400
    assert no_pr.json()["error"]["code"] == "no_pr_url"
    assert not_done.status_code == 409
    assert not_done.json()["error"]["code"] == "ticket_not_done"


@respx.mock
@pytest.mark.parametrize(
    ("status_code", "expected_code"),
    [(405, "merge_not_allowed"), (409, "merge_conflict"), (404, "pr_not_found")],
)
async def test_merge_pr_maps_github_failures(
    create_ticket,
    move_ticket,
    agent_be_client: httpx.AsyncClient,
    agent_qa_client: httpx.AsyncClient,
    status_code: int,
    expected_code: str,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")
    await agent_be_client.post(
        f"/tickets/{ticket['id']}/pr-url",
        json={"pr_url": f"https://github.com/{DEFAULT_REPO}/pull/42"},
    )
    await move_ticket(agent_be_client, ticket["id"], "IN_PROGRESS")
    await move_ticket(agent_be_client, ticket["id"], "IN_QA")
    await move_ticket(agent_qa_client, ticket["id"], "DONE")
    respx.post(f"{GITHUB_API}/app/installations/98765/access_tokens").mock(
        return_value=httpx.Response(
            201,
            json={"token": "ghs_merge", "expires_at": "2026-05-14T11:00:00Z"},
        )
    )
    respx.put(f"{GITHUB_API}/repos/{DEFAULT_REPO}/pulls/42/merge").mock(
        return_value=httpx.Response(status_code, json={"message": "merge failed"})
    )

    response = await agent_be_client.post(f"/tickets/{ticket['id']}/merge-pr")

    assert response.status_code in {404, 409}
    assert response.json()["error"]["code"] == expected_code
