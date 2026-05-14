"""Attachment domain operations."""

from __future__ import annotations

from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.domain.exceptions import (
    AttachmentContentTypeNotAllowedError,
    AttachmentNotFoundError,
    AttachmentNotReadyError,
    AttachmentTooLargeError,
    AttachmentUploadVerificationFailedError,
)
from app.domain.tickets import get_ticket
from app.enums import AttachmentStatus
from app.models.ticket_attachment import TicketAttachment
from app.storage.operations import (
    delete_object,
    generate_presigned_get_url,
    generate_presigned_put_url,
    generate_s3_key,
    get_object_size,
)
from app.storage.policy import is_content_type_allowed

logger = structlog.get_logger(__name__)


async def request_upload_url(
    session: AsyncSession,
    *,
    ticket_id: int,
    filename: str,
    content_type: str,
    size_bytes: int,
    actor: str,
) -> tuple[TicketAttachment, str]:
    settings = get_settings()

    if size_bytes <= 0 or size_bytes > settings.attachment_max_size_bytes:
        raise AttachmentTooLargeError(size_bytes, settings.attachment_max_size_bytes)
    if not is_content_type_allowed(content_type):
        raise AttachmentContentTypeNotAllowedError(content_type)

    await get_ticket(session, ticket_id)
    s3_key = generate_s3_key(ticket_id, filename)
    attachment = TicketAttachment(
        ticket_id=ticket_id,
        filename=filename,
        content_type=content_type,
        size_bytes=size_bytes,
        s3_key=s3_key,
        uploaded_by=actor,
        status=AttachmentStatus.PENDING.value,
    )
    session.add(attachment)
    await session.flush()

    upload_url = generate_presigned_put_url(s3_key, content_type, size_bytes)
    logger.info(
        "attachment.upload_url.generated",
        attachment_id=attachment.id,
        ticket_id=ticket_id,
        size_bytes=size_bytes,
        content_type=content_type,
        actor=actor,
    )
    return attachment, upload_url


async def finalize_attachment(
    session: AsyncSession,
    *,
    attachment_id: int,
    actor: str,
) -> TicketAttachment:
    attachment = await session.get(TicketAttachment, attachment_id)
    if attachment is None or attachment.deleted_at is not None:
        raise AttachmentNotFoundError(attachment_id)
    if attachment.status != AttachmentStatus.PENDING.value:
        raise AttachmentNotReadyError(attachment_id, attachment.status)

    actual_size = get_object_size(attachment.s3_key)
    if actual_size is None:
        raise AttachmentUploadVerificationFailedError(
            attachment_id,
            "object does not exist in storage",
        )
    if actual_size != attachment.size_bytes:
        delete_object(attachment.s3_key)
        attachment.status = AttachmentStatus.FAILED.value
        await session.flush()
        await session.commit()
        raise AttachmentUploadVerificationFailedError(
            attachment_id,
            f"size mismatch: declared {attachment.size_bytes}, actual {actual_size}",
        )

    now = datetime.now(UTC)
    attachment.status = AttachmentStatus.READY.value
    attachment.finalized_at = now
    attachment.uploaded_at = now
    await session.flush()

    logger.info(
        "attachment.finalized",
        attachment_id=attachment_id,
        ticket_id=attachment.ticket_id,
        actor=actor,
    )
    return attachment


async def list_attachments(
    session: AsyncSession,
    ticket_id: int,
) -> list[TicketAttachment]:
    stmt = (
        select(TicketAttachment)
        .where(
            TicketAttachment.ticket_id == ticket_id,
            TicketAttachment.status == AttachmentStatus.READY.value,
            TicketAttachment.deleted_at.is_(None),
        )
        .order_by(TicketAttachment.created_at.asc(), TicketAttachment.id.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_attachment(
    session: AsyncSession,
    attachment_id: int,
) -> TicketAttachment:
    attachment = await session.get(TicketAttachment, attachment_id)
    if attachment is None or attachment.deleted_at is not None:
        raise AttachmentNotFoundError(attachment_id)
    return attachment


async def request_download_url(
    session: AsyncSession,
    *,
    attachment_id: int,
) -> tuple[TicketAttachment, str]:
    attachment = await get_attachment(session, attachment_id)
    if attachment.status != AttachmentStatus.READY.value:
        raise AttachmentNotReadyError(attachment_id, attachment.status)

    download_url = generate_presigned_get_url(attachment.s3_key, attachment.filename)
    return attachment, download_url


async def soft_delete_attachment(
    session: AsyncSession,
    *,
    attachment_id: int,
    actor: str,
) -> TicketAttachment:
    attachment = await get_attachment(session, attachment_id)
    attachment.deleted_at = datetime.now(UTC)
    attachment.status = AttachmentStatus.DELETED.value
    await session.flush()
    logger.info(
        "attachment.soft_deleted",
        attachment_id=attachment_id,
        ticket_id=attachment.ticket_id,
        actor=actor,
    )
    return attachment


async def cleanup_pending_attachments(session: AsyncSession) -> dict[str, int]:
    """Subsystem 8 wires the scheduled cleanup job."""
    return {"pending_failed": 0, "deleted_removed": 0}
