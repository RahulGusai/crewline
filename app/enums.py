"""Enums for ticket state, agent roles, and actor kinds."""

from enum import StrEnum


class TicketStatus(StrEnum):
    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    BLOCKED = "BLOCKED"
    READY_FOR_QA = "READY_FOR_QA"
    IN_QA = "IN_QA"
    QA_FAILED = "QA_FAILED"
    DONE = "DONE"
    CANCELLED = "CANCELLED"


class AgentRole(StrEnum):
    BE = "be"
    FE = "fe"
    ARCHITECT = "architect"
    QA = "qa"


class AgentId(StrEnum):
    CORTEX = "cortex"
    LUMEN = "lumen"
    ARCHITECT = "architect"
    SENTINEL = "sentinel"


class ActorKind(StrEnum):
    AGENT = "agent"
    HUMAN = "human"
    SYSTEM = "system"


class MessageType(StrEnum):
    TICKET_ASSIGNED = "ticket_assigned"
    TICKET_UNASSIGNED = "ticket_unassigned"
    TICKET_CANCELLED = "ticket_cancelled"
    TICKET_REVIEW_REQUESTED = "ticket_review_requested"
    RPC_REQUEST = "rpc_request"
    RPC_RESPONSE = "rpc_response"
    NOTIFICATION = "notification"


SYSTEM_FIRED_TYPES: frozenset[MessageType] = frozenset(
    {
        MessageType.TICKET_ASSIGNED,
        MessageType.TICKET_UNASSIGNED,
        MessageType.TICKET_CANCELLED,
        MessageType.TICKET_REVIEW_REQUESTED,
    }
)

USER_FACING_TYPES: frozenset[MessageType] = frozenset(
    {
        MessageType.RPC_REQUEST,
        MessageType.RPC_RESPONSE,
        MessageType.NOTIFICATION,
    }
)


class RpcOutcome(StrEnum):
    ANSWERED = "answered"
    DECLINED = "declined"


class AttachmentStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    FAILED = "failed"
    DELETED = "deleted"
