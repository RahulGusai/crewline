"""HTTP routes for mailbox operations."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends, Query, status
from pydantic import Discriminator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_actor
from app.db import get_session
from app.domain.actor import Actor
from app.domain.mailbox import (
    acknowledge_message,
    list_unacked_messages,
    reject_message,
    send_notification,
    send_rpc_request,
    send_rpc_response,
)
from app.schemas.mailbox import (
    MailboxMessageRead,
    RejectMessageRequest,
    SendNotification,
    SendRpcRequest,
    SendRpcResponse,
)

router = APIRouter(prefix="/mailbox", tags=["mailbox"])

SendMessageRequest = Annotated[
    SendRpcRequest | SendRpcResponse | SendNotification,
    Discriminator("type"),
]


@router.get("", response_model=list[MailboxMessageRead])
async def get_mailbox(
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[MailboxMessageRead]:
    messages = await list_unacked_messages(
        session,
        recipient=actor.raw,
        limit=limit,
    )
    return [MailboxMessageRead.model_validate(message) for message in messages]


@router.post(
    "/messages",
    status_code=status.HTTP_201_CREATED,
    response_model=MailboxMessageRead,
)
async def send_message(
    payload: Annotated[SendMessageRequest, Body()],
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> MailboxMessageRead:
    if isinstance(payload, SendRpcRequest):
        message = await send_rpc_request(
            session,
            sender=actor.raw,
            recipient=payload.recipient,
            subject=payload.payload.subject,
            body=payload.payload.body,
            ticket_id=payload.payload.ticket_id,
        )
    elif isinstance(payload, SendRpcResponse):
        message = await send_rpc_response(
            session,
            sender=actor.raw,
            recipient=payload.recipient,
            correlation_id=payload.correlation_id,
            body=payload.payload.body,
            outcome=payload.payload.outcome,
        )
    else:
        message = await send_notification(
            session,
            sender=actor.raw,
            recipient=payload.recipient,
            subject=payload.payload.subject,
            body=payload.payload.body,
            ticket_id=payload.payload.ticket_id,
        )
    return MailboxMessageRead.model_validate(message)


@router.post("/messages/{message_id}/ack", status_code=status.HTTP_204_NO_CONTENT)
async def ack_message(
    message_id: int,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    await acknowledge_message(session, message_id=message_id, actor=actor.raw)


@router.post("/messages/{message_id}/reject", status_code=status.HTTP_204_NO_CONTENT)
async def reject_message_route(
    message_id: int,
    payload: RejectMessageRequest,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    await reject_message(
        session,
        message_id=message_id,
        actor=actor.raw,
        reason=payload.reason,
    )
