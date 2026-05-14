"""HTTP routes for GitHub App installation management."""

from __future__ import annotations

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_pm_actor
from app.config import get_settings
from app.db import get_session
from app.domain.actor import Actor
from app.domain.github import (
    consume_install_state,
    create_install_state,
    get_active_installation,
    list_installation_repo_rows,
    pm_uuid_from_actor_id,
    replace_installation_repos,
    require_active_installation,
    revoke_active_installation,
    upsert_installation,
)
from app.integrations.github import get_installation_metadata, list_installation_repos
from app.models.github_installation_repo import GitHubInstallationRepo
from app.schemas.github import GitHubInstallationStatus, GitHubRepo

router = APIRouter(prefix="/github", tags=["github"])


def _repo_schema(repo: GitHubInstallationRepo) -> GitHubRepo:
    return GitHubRepo(
        id=repo.github_repo_id,
        full_name=repo.repo_full_name,
        default_branch=repo.default_branch,
    )


@router.get("/install")
async def install_github_app_route(
    actor: Annotated[Actor, Depends(require_pm_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RedirectResponse:
    settings = get_settings()
    pm_user_id = pm_uuid_from_actor_id(actor.id)
    state = await create_install_state(session, pm_user_id)
    app_name = quote(settings.github_app_name, safe="")
    return RedirectResponse(
        f"https://github.com/apps/{app_name}/installations/new?state={state}",
        status_code=status.HTTP_302_FOUND,
    )


@router.get("/callback", response_model=None)
async def github_callback_route(
    session: Annotated[AsyncSession, Depends(get_session)],
    installation_id: Annotated[int, Query()],
    state: Annotated[str, Query()],
    setup_action: Annotated[str | None, Query()] = None,
) -> Response:
    pm_user_id = await consume_install_state(session, state)
    if pm_user_id is None:
        return HTMLResponse(
            "Installation expired, please retry.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    metadata = await get_installation_metadata(installation_id)
    account = metadata.get("account") or {}
    installation = await upsert_installation(
        session,
        pm_user_id=pm_user_id,
        installation_id=installation_id,
        account_login=str(account.get("login") or ""),
        account_type=str(account.get("type") or "User"),
    )
    repos = await list_installation_repos(installation.installation_id)
    await replace_installation_repos(
        session,
        installation_id=installation.installation_id,
        repos=repos,
    )
    return RedirectResponse(get_settings().github_frontend_redirect_url)


@router.get("/installation", response_model=GitHubInstallationStatus)
async def get_installation_status_route(
    actor: Annotated[Actor, Depends(require_pm_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> GitHubInstallationStatus:
    installation = await get_active_installation(session, pm_uuid_from_actor_id(actor.id))
    if installation is None:
        return GitHubInstallationStatus(connected=False)

    repos = await list_installation_repo_rows(session, installation.installation_id)
    return GitHubInstallationStatus(
        connected=True,
        account_login=installation.account_login,
        account_type=installation.account_type,
        installed_at=installation.installed_at,
        repos=[_repo_schema(repo) for repo in repos],
    )


@router.get("/repos", response_model=list[GitHubRepo])
async def list_github_repos_route(
    actor: Annotated[Actor, Depends(require_pm_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[GitHubRepo]:
    installation = await require_active_installation(session, pm_uuid_from_actor_id(actor.id))
    repos = await list_installation_repo_rows(session, installation.installation_id)
    return [_repo_schema(repo) for repo in repos]


@router.post("/refresh-repos", response_model=list[GitHubRepo])
async def refresh_github_repos_route(
    actor: Annotated[Actor, Depends(require_pm_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[GitHubRepo]:
    installation = await require_active_installation(session, pm_uuid_from_actor_id(actor.id))
    repos = await list_installation_repos(installation.installation_id)
    rows = await replace_installation_repos(
        session,
        installation_id=installation.installation_id,
        repos=repos,
    )
    return [_repo_schema(repo) for repo in rows]


@router.post("/disconnect", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_github_route(
    actor: Annotated[Actor, Depends(require_pm_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    await revoke_active_installation(session, pm_uuid_from_actor_id(actor.id))
