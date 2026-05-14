"""GitHub App API helpers."""

from __future__ import annotations

import time
from typing import Any

import httpx
import jwt

from app.config import get_settings
from app.domain.exceptions import GitHubApiError, GitHubTokenMintFailedError

GITHUB_API = "https://api.github.com"


def generate_app_jwt() -> str:
    """Return a GitHub App JWT signed with the configured private key."""
    settings = get_settings()
    if settings.github_app_id is None or settings.github_app_private_key is None:
        raise GitHubTokenMintFailedError("GitHub App credentials are not configured")

    private_key = settings.github_app_private_key.replace("\\n", "\n")
    if not private_key.startswith("-----BEGIN"):
        if settings.environment in {"development", "test"}:
            return f"test-github-app-jwt-{settings.github_app_id}"
        raise GitHubTokenMintFailedError("GitHub App private key is invalid")

    now = int(time.time())
    payload = {
        "iat": now - 60,
        "exp": now + 600,
        "iss": settings.github_app_id,
    }
    return jwt.encode(payload, private_key, algorithm="RS256")


async def get_installation_metadata(installation_id: int) -> dict[str, Any]:
    jwt_token = generate_app_jwt()
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{GITHUB_API}/app/installations/{installation_id}",
            headers={
                "Authorization": f"Bearer {jwt_token}",
                "Accept": "application/vnd.github+json",
            },
        )
    if response.status_code != 200:
        raise GitHubApiError(response.status_code, response.text)
    return dict(response.json())


async def get_installation_token(
    installation_id: int,
    repository_ids: list[int] | None = None,
) -> dict[str, Any]:
    """Mint an installation token, optionally restricted to repository ids."""
    jwt_token = generate_app_jwt()
    body: dict[str, Any] = {}
    if repository_ids:
        body["repository_ids"] = repository_ids

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{GITHUB_API}/app/installations/{installation_id}/access_tokens",
            headers={
                "Authorization": f"Bearer {jwt_token}",
                "Accept": "application/vnd.github+json",
            },
            json=body,
        )
    if response.status_code != 201:
        raise GitHubTokenMintFailedError(f"GitHub returned {response.status_code}")
    return dict(response.json())


async def list_installation_repos(installation_id: int) -> list[dict[str, Any]]:
    """List all repositories accessible to an installation."""
    token_response = await get_installation_token(installation_id)
    token = token_response["token"]
    repos: list[dict[str, Any]] = []
    page = 1

    async with httpx.AsyncClient() as client:
        while True:
            response = await client.get(
                f"{GITHUB_API}/installation/repositories",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                },
                params={"per_page": 100, "page": page},
            )
            if response.status_code != 200:
                raise GitHubApiError(response.status_code, response.text)
            data = response.json()
            page_repos = list(data.get("repositories", []))
            repos.extend(page_repos)
            if len(page_repos) < 100:
                break
            page += 1
    return repos


class GitHubMergeError(Exception):
    """Raised when GitHub rejects a merge request."""

    def __init__(self, status_code: int, data: dict[str, Any]) -> None:
        self.status_code = status_code
        self.data = data
        super().__init__(f"GitHub merge failed with {status_code}")


async def merge_pull_request(
    installation_id: int,
    repository_id: int,
    owner: str,
    repo: str,
    pr_number: int,
    *,
    merge_method: str = "squash",
    commit_title: str | None = None,
    commit_message: str | None = None,
) -> dict[str, Any]:
    """Merge a pull request using an installation token scoped to one repo."""
    token_response = await get_installation_token(installation_id, [repository_id])
    token = token_response["token"]
    body: dict[str, Any] = {"merge_method": merge_method}
    if commit_title:
        body["commit_title"] = commit_title
    if commit_message:
        body["commit_message"] = commit_message

    async with httpx.AsyncClient() as client:
        response = await client.put(
            f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}/merge",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
            json=body,
        )

    data = response.json() if response.content else {}
    if response.status_code == 200:
        return dict(data)
    raise GitHubMergeError(response.status_code, dict(data))
