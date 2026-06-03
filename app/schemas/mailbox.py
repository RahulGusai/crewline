"""Pydantic schemas for mailbox messages."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.enums import MessageType, RpcOutcome
from app.schemas.common import BaseSchema, StrictSchema


class TicketAssignedPayload(StrictSchema):
    ticket_id: int
    title: str
    assigned_by: str


class TicketUnassignedPayload(StrictSchema):
    ticket_id: int
    unassigned_by: str


class TicketCancelledPayload(StrictSchema):
    ticket_id: int
    cancelled_by: str
    reason: str | None = None


class TicketReviewRequestedPayload(StrictSchema):
    ticket_id: int
    requested_by: str


class RpcRequestPayload(StrictSchema):
    subject: str
    body: str
    ticket_id: int
    repo_url: str | None = None


class RpcResponsePayload(StrictSchema):
    body: str
    outcome: RpcOutcome


class NotificationPayload(StrictSchema):
    subject: str
    body: str
    ticket_id: int | None = None


class MailboxMessageRead(BaseSchema):
    id: int
    type: MessageType
    sender: str
    recipient: str
    payload: dict[str, Any]
    requires_response: bool
    correlation_id: int | None
    created_at: datetime


class SendRpcRequest(StrictSchema):
    type: Literal[MessageType.RPC_REQUEST]
    recipient: str
    payload: RpcRequestPayload


class SendRpcResponse(StrictSchema):
    type: Literal[MessageType.RPC_RESPONSE]
    recipient: str
    correlation_id: int
    payload: RpcResponsePayload


class SendNotification(StrictSchema):
    type: Literal[MessageType.NOTIFICATION]
    recipient: str
    payload: NotificationPayload


class RejectMessageRequest(StrictSchema):
    reason: str = Field(..., min_length=1)
