"""Domain helpers for GitHub App installations and repository access."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.actor import PM_USER_ID
from app.domain.exceptions import (
    GitHubInstallationInactiveError,
    GitHubNotConnectedError,
    RelatedRepoInvalidError,
    RepoNotAccessibleError,
)
from app.models.github_install_state import GitHubInstallState
from app.models.github_installation import GitHubInstallation
from app.models.github_installation_repo import GitHubInstallationRepo

GITHUB_STATE_TTL_MINUTES = 10


def pm_uuid_from_actor_id(actor_id: str) -> UUID:
    if actor_id == "pm":
        actor_id = PM_USER_ID
    return UUID(actor_id)


async def create_install_state(session: AsyncSession, pm_user_id: UUID) -> str:
    state = secrets.token_urlsafe(32)
    session.add(GitHubInstallState(state=state, pm_user_id=pm_user_id))
    await session.flush()
    return state


async def consume_install_state(session: AsyncSession, state: str) -> UUID | None:
    row = await session.get(GitHubInstallState, state)
    if row is None:
        return None

    await session.delete(row)
    cutoff = datetime.now(UTC) - timedelta(minutes=GITHUB_STATE_TTL_MINUTES)
    if row.created_at < cutoff:
        await session.flush()
        return None

    await session.flush()
    return row.pm_user_id


async def get_active_installation(
    session: AsyncSession,
    pm_user_id: UUID,
) -> GitHubInstallation | None:
    result = await session.execute(
        select(GitHubInstallation).where(
            GitHubInstallation.pm_user_id == pm_user_id,
            GitHubInstallation.status == "active",
        )
    )
    return result.scalar_one_or_none()


async def require_active_installation(
    session: AsyncSession,
    pm_user_id: UUID,
) -> GitHubInstallation:
    installation = await get_active_installation(session, pm_user_id)
    if installation is None:
        raise GitHubNotConnectedError()
    return installation


async def require_active_installation_for_ticket_pm(
    session: AsyncSession,
    pm_user_id: UUID,
) -> GitHubInstallation:
    result = await session.execute(
        select(GitHubInstallation)
        .where(GitHubInstallation.pm_user_id == pm_user_id)
        .order_by(GitHubInstallation.installed_at.desc())
    )
    installation = result.scalars().first()
    if installation is None:
        raise GitHubNotConnectedError()
    if installation.status != "active":
        raise GitHubInstallationInactiveError(installation.installation_id)
    return installation


async def upsert_installation(
    session: AsyncSession,
    *,
    pm_user_id: UUID,
    installation_id: int,
    account_login: str,
    account_type: str,
) -> GitHubInstallation:
    await session.execute(
        update(GitHubInstallation)
        .where(
            GitHubInstallation.pm_user_id == pm_user_id,
            GitHubInstallation.installation_id != installation_id,
            GitHubInstallation.status == "active",
        )
        .values(status="revoked", revoked_at=datetime.now(UTC))
    )

    existing = await session.execute(
        select(GitHubInstallation).where(GitHubInstallation.installation_id == installation_id)
    )
    installation = existing.scalar_one_or_none()
    if installation is None:
        installation = GitHubInstallation(
            pm_user_id=pm_user_id,
            installation_id=installation_id,
            account_login=account_login,
            account_type=account_type,
            status="active",
            revoked_at=None,
        )
        session.add(installation)
    else:
        installation.pm_user_id = pm_user_id
        installation.account_login = account_login
        installation.account_type = account_type
        installation.status = "active"
        installation.revoked_at = None
    await session.flush()
    return installation


async def replace_installation_repos(
    session: AsyncSession,
    *,
    installation_id: int,
    repos: list[dict[str, Any]],
) -> list[GitHubInstallationRepo]:
    await session.execute(
        delete(GitHubInstallationRepo).where(
            GitHubInstallationRepo.installation_id == installation_id
        )
    )
    rows: list[GitHubInstallationRepo] = []
    for repo in repos:
        row = GitHubInstallationRepo(
            installation_id=installation_id,
            github_repo_id=int(repo["id"]),
            repo_full_name=str(repo["full_name"]),
            default_branch=str(repo.get("default_branch") or "main"),
        )
        session.add(row)
        rows.append(row)
    await session.flush()
    return rows


async def list_installation_repo_rows(
    session: AsyncSession,
    installation_id: int,
) -> list[GitHubInstallationRepo]:
    result = await session.execute(
        select(GitHubInstallationRepo)
        .where(GitHubInstallationRepo.installation_id == installation_id)
        .order_by(GitHubInstallationRepo.repo_full_name.asc())
    )
    return list(result.scalars().all())


async def require_repo_access(
    session: AsyncSession,
    *,
    installation_id: int,
    repo_full_name: str,
) -> GitHubInstallationRepo:
    result = await session.execute(
        select(GitHubInstallationRepo).where(
            GitHubInstallationRepo.installation_id == installation_id,
            GitHubInstallationRepo.repo_full_name == repo_full_name,
        )
    )
    repo = result.scalar_one_or_none()
    if repo is None:
        raise RepoNotAccessibleError(repo_full_name)
    return repo


async def validate_ticket_repos(
    session: AsyncSession,
    *,
    installation_id: int,
    repo_full_name: str,
    related_repo_full_names: list[str],
) -> None:
    await require_repo_access(
        session,
        installation_id=installation_id,
        repo_full_name=repo_full_name,
    )
    seen: set[str] = set()
    for related in related_repo_full_names:
        if related == repo_full_name:
            raise RelatedRepoInvalidError(related, "related repo cannot equal primary repo")
        if related in seen:
            raise RelatedRepoInvalidError(related, "duplicate related repo")
        seen.add(related)
        try:
            await require_repo_access(
                session,
                installation_id=installation_id,
                repo_full_name=related,
            )
        except RepoNotAccessibleError as exc:
            raise RelatedRepoInvalidError(related, "repo is not accessible") from exc


async def revoke_active_installation(session: AsyncSession, pm_user_id: UUID) -> None:
    await session.execute(
        update(GitHubInstallation)
        .where(
            GitHubInstallation.pm_user_id == pm_user_id,
            GitHubInstallation.status == "active",
        )
        .values(status="revoked", revoked_at=datetime.now(UTC))
    )
    await session.flush()


async def require_installation_by_id(
    session: AsyncSession,
    installation_id: int,
) -> GitHubInstallation:
    result = await session.execute(
        select(GitHubInstallation).where(
            GitHubInstallation.installation_id == installation_id,
            GitHubInstallation.status == "active",
        )
    )
    installation = result.scalar_one_or_none()
    if installation is None:
        raise GitHubInstallationInactiveError(installation_id)
    return installation
