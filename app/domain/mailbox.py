"""Mailbox domain operations."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

import structlog
from sqlalchemy import Integer, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.actor import Actor, parse_actor
from app.domain.exceptions import (
    CorrelationIdMismatchError,
    InvalidMessageTypeError,
    MailboxMessageNotFoundError,
    MessageStateConflictError,
)
from app.enums import SYSTEM_FIRED_TYPES, USER_FACING_TYPES, ActorKind, MessageType, RpcOutcome
from app.models.mailbox_message import MailboxMessage
from app.schemas.mailbox import (
    NotificationPayload,
    RpcRequestPayload,
    RpcResponsePayload,
    TicketAssignedPayload,
    TicketCancelledPayload,
    TicketReviewRequestedPayload,
    TicketUnassignedPayload,
)

logger = structlog.get_logger(__name__)


async def send_ticket_assigned(
    session: AsyncSession,
    *,
    ticket_id: int,
    title: str,
    recipient: str,
    sender: str,
) -> MailboxMessage:
    payload = TicketAssignedPayload(ticket_id=ticket_id, title=title, assigned_by=sender)
    return await _insert_message(
        session,
        type=MessageType.TICKET_ASSIGNED,
        sender=sender,
        recipient=recipient,
        payload=payload.model_dump(mode="json"),
        requires_response=False,
    )


async def send_ticket_unassigned(
    session: AsyncSession,
    *,
    ticket_id: int,
    recipient: str,
    sender: str,
) -> MailboxMessage:
    payload = TicketUnassignedPayload(ticket_id=ticket_id, unassigned_by=sender)
    return await _insert_message(
        session,
        type=MessageType.TICKET_UNASSIGNED,
        sender=sender,
        recipient=recipient,
        payload=payload.model_dump(mode="json"),
        requires_response=False,
    )


async def send_ticket_cancelled(
    session: AsyncSession,
    *,
    ticket_id: int,
    recipient: str,
    sender: str,
    reason: str | None = None,
) -> MailboxMessage:
    payload = TicketCancelledPayload(ticket_id=ticket_id, cancelled_by=sender, reason=reason)
    return await _insert_message(
        session,
        type=MessageType.TICKET_CANCELLED,
        sender=sender,
        recipient=recipient,
        payload=payload.model_dump(mode="json"),
        requires_response=False,
    )


async def send_ticket_review_requested(
    session: AsyncSession,
    *,
    ticket_id: int,
    recipient: str,
    sender: str,
) -> MailboxMessage:
    payload = TicketReviewRequestedPayload(ticket_id=ticket_id, requested_by=sender)
    return await _insert_message(
        session,
        type=MessageType.TICKET_REVIEW_REQUESTED,
        sender=sender,
        recipient=recipient,
        payload=payload.model_dump(mode="json"),
        requires_response=False,
    )


async def send_rpc_request(
    session: AsyncSession,
    *,
    sender: str,
    recipient: str,
    subject: str,
    body: str,
    ticket_id: int,
) -> MailboxMessage:
    payload = RpcRequestPayload(subject=subject, body=body, ticket_id=ticket_id)
    return await _insert_message(
        session,
        type=MessageType.RPC_REQUEST,
        sender=sender,
        recipient=recipient,
        payload=payload.model_dump(mode="json"),
        requires_response=True,
    )


async def send_rpc_response(
    session: AsyncSession,
    *,
    sender: str,
    recipient: str,
    correlation_id: int,
    body: str,
    outcome: RpcOutcome,
) -> MailboxMessage:
    original = await session.get(MailboxMessage, correlation_id)
    if original is None:
        raise CorrelationIdMismatchError(correlation_id, "no such message")
    if original.type != MessageType.RPC_REQUEST.value:
        raise CorrelationIdMismatchError(correlation_id, "referenced message is not an rpc_request")
    if original.sender != recipient:
        raise CorrelationIdMismatchError(
            correlation_id,
            "recipient must be the sender of the original request",
        )

    existing_response = await session.execute(
        select(MailboxMessage).where(
            MailboxMessage.correlation_id == correlation_id,
            MailboxMessage.type == MessageType.RPC_RESPONSE.value,
        )
    )
    if existing_response.scalar_one_or_none() is not None:
        raise CorrelationIdMismatchError(correlation_id, "this request has already been responded to")

    payload = RpcResponsePayload(body=body, outcome=outcome)
    return await _insert_message(
        session,
        type=MessageType.RPC_RESPONSE,
        sender=sender,
        recipient=recipient,
        payload=payload.model_dump(mode="json"),
        requires_response=False,
        correlation_id=correlation_id,
    )


async def send_notification(
    session: AsyncSession,
    *,
    sender: str,
    recipient: str,
    subject: str,
    body: str,
    ticket_id: int | None = None,
) -> MailboxMessage:
    payload = NotificationPayload(subject=subject, body=body, ticket_id=ticket_id)
    return await _insert_message(
        session,
        type=MessageType.NOTIFICATION,
        sender=sender,
        recipient=recipient,
        payload=payload.model_dump(mode="json"),
        requires_response=False,
    )


async def validate_user_sendable_type(message_type: MessageType) -> None:
    if message_type in SYSTEM_FIRED_TYPES or message_type not in USER_FACING_TYPES:
        raise InvalidMessageTypeError(message_type.value)


async def list_unacked_messages(
    session: AsyncSession,
    *,
    recipient: str,
    limit: int,
) -> list[MailboxMessage]:
    stmt = (
        select(MailboxMessage)
        .where(
            MailboxMessage.recipient == recipient,
            MailboxMessage.acknowledged_at.is_(None),
            MailboxMessage.rejected_at.is_(None),
        )
        .order_by(MailboxMessage.created_at.asc(), MailboxMessage.id.asc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_messages_for_ticket(
    session: AsyncSession,
    *,
    ticket_id: int,
    actor: Actor,
) -> list[MailboxMessage]:
    """Return mailbox messages tied to a ticket, ordered oldest-first.

    Caller is responsible for ticket existence and ownership authorization.
    PMs see all ticket messages; owning agents see messages they sent or received.
    """
    requests_on_ticket = (
        select(MailboxMessage.id)
        .where(MailboxMessage.payload["ticket_id"].astext.cast(Integer) == ticket_id)
        .where(MailboxMessage.type == MessageType.RPC_REQUEST.value)
    )
    stmt = (
        select(MailboxMessage)
        .where(
            or_(
                MailboxMessage.payload["ticket_id"].astext.cast(Integer) == ticket_id,
                MailboxMessage.correlation_id.in_(requests_on_ticket),
            )
        )
        .order_by(MailboxMessage.created_at.asc(), MailboxMessage.id.asc())
    )
    if actor.kind == ActorKind.AGENT:
        stmt = stmt.where(
            or_(
                MailboxMessage.sender == actor.raw,
                MailboxMessage.recipient == actor.raw,
            )
        )

    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_message(session: AsyncSession, message_id: int) -> MailboxMessage:
    message = await session.get(MailboxMessage, message_id)
    if message is None:
        raise MailboxMessageNotFoundError(message_id)
    return message


async def acknowledge_message(
    session: AsyncSession,
    *,
    message_id: int,
    actor: str,
) -> MailboxMessage:
    message = await get_message(session, message_id)
    if message.recipient != actor:
        raise MailboxMessageNotFoundError(message_id)
    if message.rejected_at is not None:
        raise MessageStateConflictError(message_id, "rejected", "ack")
    if message.acknowledged_at is not None:
        return message

    result = cast(
        CursorResult[Any],
        await session.execute(
            update(MailboxMessage)
            .where(
                MailboxMessage.id == message_id,
                MailboxMessage.acknowledged_at.is_(None),
                MailboxMessage.rejected_at.is_(None),
            )
            .values(acknowledged_at=datetime.now(UTC))
        ),
    )
    await session.flush()
    if result.rowcount == 0:
        await session.refresh(message)
        if message.rejected_at is not None:
            raise MessageStateConflictError(message_id, "rejected", "ack")

    await session.refresh(message)
    logger.info("mailbox.message.acknowledged", message_id=message_id, actor=actor, type=message.type)
    return message


async def reject_message(
    session: AsyncSession,
    *,
    message_id: int,
    actor: str,
    reason: str,
) -> MailboxMessage:
    message = await get_message(session, message_id)
    if message.recipient != actor:
        raise MailboxMessageNotFoundError(message_id)
    if message.acknowledged_at is not None:
        raise MessageStateConflictError(message_id, "acknowledged", "reject")
    if message.rejected_at is not None:
        return message

    result = cast(
        CursorResult[Any],
        await session.execute(
            update(MailboxMessage)
            .where(
                MailboxMessage.id == message_id,
                MailboxMessage.acknowledged_at.is_(None),
                MailboxMessage.rejected_at.is_(None),
            )
            .values(rejected_at=datetime.now(UTC), rejection_reason=reason)
        ),
    )
    await session.flush()
    if result.rowcount == 0:
        await session.refresh(message)
        if message.acknowledged_at is not None:
            raise MessageStateConflictError(message_id, "acknowledged", "reject")

    await session.refresh(message)
    logger.info("mailbox.message.rejected", message_id=message_id, actor=actor, type=message.type)
    return message


async def _insert_message(
    session: AsyncSession,
    *,
    type: MessageType,
    sender: str,
    recipient: str,
    payload: dict[str, Any],
    requires_response: bool,
    correlation_id: int | None = None,
) -> MailboxMessage:
    parse_actor(sender)
    parse_actor(recipient)
    message = MailboxMessage(
        type=type.value,
        sender=sender,
        recipient=recipient,
        payload=payload,
        requires_response=requires_response,
        correlation_id=correlation_id,
    )
    session.add(message)
    await session.flush()
    logger.info(
        "mailbox.message.sent",
        message_id=message.id,
        type=type.value,
        sender=sender,
        recipient=recipient,
        requires_response=requires_response,
        correlation_id=correlation_id,
    )
    return message
