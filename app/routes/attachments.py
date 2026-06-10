"""HTTP routes for ticket attachments."""

from __future__ import annotations

from typing import Annotated
from urllib.parse import quote

import structlog
from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_actor, require_pm_actor
from app.auth.permissions import require_ticket_read_access
from app.config import get_settings
from app.db import get_session
from app.domain.actor import Actor
from app.domain.attachments import (
    finalize_attachment,
    get_attachment,
    list_attachments,
    open_attachment_content,
    request_download_url,
    request_upload_url,
    soft_delete_attachment,
)
from app.domain.exceptions import ActorNotPermittedError, AttachmentNotFoundError
from app.domain.tickets import get_ticket
from app.enums import ActorKind
from app.schemas.attachment import (
    AttachmentDownloadResponse,
    AttachmentRead,
    AttachmentUploadRequest,
    AttachmentUploadResponse,
)

router = APIRouter(prefix="/tickets", tags=["attachments"])
logger = structlog.get_logger(__name__)


def _check_ticket_access(actor: Actor, ticket_id: int, owner_agent_id: str | None) -> None:
    if actor.kind == ActorKind.AGENT and owner_agent_id != actor.id:
        raise ActorNotPermittedError(
            actor=actor.raw,
            action=f"access attachments on ticket {ticket_id}",
        )


@router.post(
    "/{ticket_id}/attachments/upload-url",
    status_code=status.HTTP_201_CREATED,
    response_model=AttachmentUploadResponse,
)
async def request_upload_url_route(
    ticket_id: int,
    payload: AttachmentUploadRequest,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AttachmentUploadResponse:
    logger.debug(
        "attachments.upload_url.payload",
        actor=actor.raw,
        ticket_id=ticket_id,
        payload=payload.model_dump(mode="json"),
    )
    settings = get_settings()
    ticket = await get_ticket(session, ticket_id)
    _check_ticket_access(actor, ticket.id, ticket.owner_agent_id)
    attachment, upload_url = await request_upload_url(
        session,
        ticket_id=ticket_id,
        filename=payload.filename,
        content_type=payload.content_type,
        size_bytes=payload.size_bytes,
        actor=actor.raw,
    )
    return AttachmentUploadResponse(
        attachment_id=attachment.id,
        upload_url=upload_url,
        expires_in_seconds=settings.attachment_upload_url_ttl_seconds,
    )


@router.post(
    "/{ticket_id}/attachments/{attachment_id}/finalize",
    status_code=status.HTTP_200_OK,
    response_model=AttachmentRead,
)
async def finalize_route(
    ticket_id: int,
    attachment_id: int,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AttachmentRead:
    ticket = await get_ticket(session, ticket_id)
    _check_ticket_access(actor, ticket.id, ticket.owner_agent_id)
    attachment = await get_attachment(session, attachment_id)
    if attachment.ticket_id != ticket_id:
        raise AttachmentNotFoundError(attachment_id)
    finalized = await finalize_attachment(
        session,
        attachment_id=attachment_id,
        actor=actor.raw,
    )
    return AttachmentRead.model_validate(finalized)


@router.get(
    "/{ticket_id}/attachments",
    response_model=list[AttachmentRead],
)
async def list_attachments_route(
    ticket_id: int,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[AttachmentRead]:
    ticket = await get_ticket(session, ticket_id)
    await require_ticket_read_access(session, actor, ticket, f"list attachments on ticket {ticket_id}")
    attachments = await list_attachments(session, ticket_id)
    return [AttachmentRead.model_validate(attachment) for attachment in attachments]


@router.get(
    "/{ticket_id}/attachments/{attachment_id}/download-url",
    response_model=AttachmentDownloadResponse,
)
async def request_download_url_route(
    ticket_id: int,
    attachment_id: int,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AttachmentDownloadResponse:
    settings = get_settings()
    ticket = await get_ticket(session, ticket_id)
    await require_ticket_read_access(session, actor, ticket, f"download attachment on ticket {ticket_id}")
    attachment = await get_attachment(session, attachment_id)
    if attachment.ticket_id != ticket_id:
        raise AttachmentNotFoundError(attachment_id)
    attachment, download_url = await request_download_url(session, attachment_id=attachment_id)
    return AttachmentDownloadResponse(
        download_url=download_url,
        expires_in_seconds=settings.attachment_download_url_ttl_seconds,
        filename=attachment.filename,
    )


@router.get(
    "/{ticket_id}/attachments/{attachment_id}/content",
)
async def get_attachment_content_route(
    ticket_id: int,
    attachment_id: int,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> StreamingResponse:
    ticket = await get_ticket(session, ticket_id)
    await require_ticket_read_access(session, actor, ticket, f"download attachment on ticket {ticket_id}")
    attachment, stream, content_length = await open_attachment_content(
        session,
        ticket_id=ticket_id,
        attachment_id=attachment_id,
    )
    filename = (
        attachment.filename.replace("\\", "/")
        .rsplit("/", 1)[-1]
        .replace("\r", "_")
        .replace("\n", "_")
        .replace('"', '\\"')
    )
    headers = {
        "Content-Disposition": (
            f'attachment; filename="{filename}"; filename*=UTF-8\'\'{quote(attachment.filename, safe="")}'
        ),
        "Content-Length": str(content_length if content_length is not None else attachment.size_bytes),
    }
    return StreamingResponse(
        stream,
        media_type=attachment.content_type,
        headers=headers,
    )


@router.delete(
    "/{ticket_id}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_attachment_route(
    ticket_id: int,
    attachment_id: int,
    actor: Annotated[Actor, Depends(require_pm_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    ticket = await get_ticket(session, ticket_id)
    _check_ticket_access(actor, ticket.id, ticket.owner_agent_id)
    attachment = await get_attachment(session, attachment_id)
    if attachment.ticket_id != ticket_id:
        raise AttachmentNotFoundError(attachment_id)
    await soft_delete_attachment(
        session,
        attachment_id=attachment_id,
        actor=actor.raw,
    )
