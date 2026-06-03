"""Ticket-scoped GitHub runtime endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_actor
from app.auth.permissions import require_agent_ticket_read_access
from app.db import get_session
from app.domain.agents import get_agent
from app.domain.actor import Actor, parse_actor
from app.domain.exceptions import (
    ActorNotPermittedError,
    GitHubApiError,
    MergeConflictError,
    MergeNotAllowedError,
    NoPrUrlError,
    PrNotFoundError,
    RepoNotAccessibleError,
    TicketNotDoneError,
)
from app.domain.github import (
    pm_uuid_from_actor_id,
    require_active_installation_for_ticket_pm,
    require_repo_access,
)
from app.domain.tickets import get_ticket, parse_github_pr_url, set_ticket_pr_url
from app.enums import ActorKind, AgentRole, TicketStatus
from app.integrations.github import GitHubMergeError, get_installation_token, merge_pull_request
from app.models.ticket import Ticket
from app.models.ticket_audit_log import TicketAuditLog
from app.schemas.github import GitHubTokenRequest, GitHubTokenResponse, MergePrResponse
from app.schemas.ticket import TicketPrUrlUpdate, TicketRead

router = APIRouter(prefix="/tickets", tags=["github"])


def _require_agent_owner(actor: Actor, ticket: Ticket, action: str) -> None:
    if actor.kind != ActorKind.AGENT or ticket.owner_agent_id != actor.id:
        raise ActorNotPermittedError(actor=actor.raw, action=action)


async def _require_agent_owner_or_historical_owner(
    session: AsyncSession,
    actor: Actor,
    ticket: Ticket,
    action: str,
) -> None:
    if actor.kind != ActorKind.AGENT:
        raise ActorNotPermittedError(actor=actor.raw, action=action)
    if ticket.owner_agent_id == actor.id:
        return

    agent = await get_agent(session, actor.id)
    if agent.role == AgentRole.QA.value:
        return

    result = await session.execute(
        select(TicketAuditLog.id).where(
            TicketAuditLog.ticket_id == ticket.id,
            TicketAuditLog.to_owner == actor.id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise ActorNotPermittedError(actor=actor.raw, action=action)


def _parse_github_expires_at(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _pm_user_id_from_ticket(ticket: Ticket) -> str:
    actor = parse_actor(ticket.created_by)
    return actor.id


@router.post(
    "/{ticket_id}/github-token",
    response_model=GitHubTokenResponse,
)
async def mint_github_token_route(
    ticket_id: int,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
    payload: GitHubTokenRequest | None = None,
) -> GitHubTokenResponse:
    ticket = await get_ticket(session, ticket_id)
    await require_agent_ticket_read_access(session, actor, ticket, f"mint GitHub token for ticket {ticket_id}")
    target_repo = payload.repo_full_name if payload and payload.repo_full_name else ticket.repo_full_name
    if target_repo != ticket.repo_full_name and target_repo not in ticket.related_repo_full_names:
        raise RepoNotAccessibleError(target_repo)

    installation = await require_active_installation_for_ticket_pm(
        session,
        pm_uuid_from_actor_id(_pm_user_id_from_ticket(ticket)),
    )
    repo = await require_repo_access(
        session,
        installation_id=installation.installation_id,
        repo_full_name=target_repo,
    )
    token_response = await get_installation_token(
        installation.installation_id,
        repository_ids=[repo.github_repo_id],
    )
    token = str(token_response["token"])
    return GitHubTokenResponse(
        token=token,
        expires_at=_parse_github_expires_at(str(token_response["expires_at"])),
        clone_url=f"https://x-access-token:{token}@github.com/{target_repo}.git",
        repo_full_name=target_repo,
    )


@router.post(
    "/{ticket_id}/pr-url",
    status_code=status.HTTP_200_OK,
    response_model=TicketRead,
)
async def set_pr_url_route(
    ticket_id: int,
    payload: TicketPrUrlUpdate,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TicketRead:
    ticket = await set_ticket_pr_url(
        session,
        ticket_id=ticket_id,
        actor=actor.raw,
        pr_url=payload.pr_url,
    )
    await session.refresh(ticket)
    return TicketRead.model_validate(ticket)


@router.post("/{ticket_id}/merge-pr", response_model=MergePrResponse)
async def merge_pr_route(
    ticket_id: int,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> MergePrResponse:
    ticket = await get_ticket(session, ticket_id)
    await _require_agent_owner_or_historical_owner(
        session,
        actor,
        ticket,
        f"merge PR for ticket {ticket_id}",
    )
    if ticket.pr_url is None:
        raise NoPrUrlError(ticket_id)
    if ticket.status != TicketStatus.DONE.value:
        raise TicketNotDoneError(ticket_id, ticket.status)

    owner, repo_name, pr_number = parse_github_pr_url(ticket.pr_url)
    installation = await require_active_installation_for_ticket_pm(
        session,
        pm_uuid_from_actor_id(_pm_user_id_from_ticket(ticket)),
    )
    repo = await require_repo_access(
        session,
        installation_id=installation.installation_id,
        repo_full_name=ticket.repo_full_name,
    )

    try:
        result = await merge_pull_request(
            installation.installation_id,
            repo.github_repo_id,
            owner,
            repo_name,
            pr_number,
            commit_title=f"{ticket.title} (#{pr_number})",
            commit_message=f"Crewline ticket #{ticket.id}",
        )
    except GitHubMergeError as exc:
        message = str(exc.data.get("message") or "")
        if exc.status_code == 405 and "already merged" in message.lower():
            return MergePrResponse(merged=True, message=message)
        if exc.status_code == 405:
            raise MergeNotAllowedError(message) from exc
        if exc.status_code == 409:
            raise MergeConflictError(message) from exc
        if exc.status_code == 404:
            raise PrNotFoundError(ticket.pr_url) from exc
        raise GitHubApiError(exc.status_code, message) from exc

    return MergePrResponse(
        merged=True,
        sha=result.get("sha"),
        message=result.get("message"),
    )
