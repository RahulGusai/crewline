"""Authoritative ticket workflow state machine."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.actor import Actor
from app.domain.exceptions import (
    ActorNotPermittedError,
    InvalidTransitionError,
    OverrideNotPermittedError,
    ReasonRequiredError,
)
from app.enums import ActorKind, TicketKind, TicketStatus
from app.models.agent import Agent
from app.models.ticket import Ticket


class AllowedActorCategory(StrEnum):
    OWNER = "owner"
    PM = "pm"
    ROLE_QA = "role:qa"


@dataclass(frozen=True)
class TransitionRule:
    allowed_actor: AllowedActorCategory
    reason_required: bool
    pm_override_required: bool


TRANSITION_RULES: dict[tuple[TicketStatus | None, TicketStatus], TransitionRule] = {
    (None, TicketStatus.TODO): TransitionRule(AllowedActorCategory.PM, False, False),
    (TicketStatus.TODO, TicketStatus.IN_PROGRESS): TransitionRule(
        AllowedActorCategory.OWNER,
        False,
        False,
    ),
    (TicketStatus.TODO, TicketStatus.BLOCKED): TransitionRule(
        AllowedActorCategory.OWNER,
        True,
        False,
    ),
    (TicketStatus.IN_PROGRESS, TicketStatus.BLOCKED): TransitionRule(
        AllowedActorCategory.OWNER,
        True,
        False,
    ),
    (TicketStatus.BLOCKED, TicketStatus.IN_PROGRESS): TransitionRule(
        AllowedActorCategory.OWNER,
        False,
        False,
    ),
    (TicketStatus.IN_PROGRESS, TicketStatus.IN_QA): TransitionRule(
        AllowedActorCategory.OWNER,
        False,
        False,
    ),
    (TicketStatus.IN_QA, TicketStatus.DONE): TransitionRule(
        AllowedActorCategory.ROLE_QA,
        False,
        False,
    ),
    (TicketStatus.IN_QA, TicketStatus.QA_FAILED): TransitionRule(
        AllowedActorCategory.ROLE_QA,
        True,
        False,
    ),
    (TicketStatus.QA_FAILED, TicketStatus.TODO): TransitionRule(
        AllowedActorCategory.OWNER,
        False,
        False,
    ),
}

TEST_ONLY_TRANSITION_RULES: dict[tuple[TicketStatus | None, TicketStatus], TransitionRule] = {
    (None, TicketStatus.TODO): TransitionRule(AllowedActorCategory.PM, False, False),
    (TicketStatus.TODO, TicketStatus.IN_PROGRESS): TransitionRule(
        AllowedActorCategory.OWNER,
        False,
        False,
    ),
    (TicketStatus.TODO, TicketStatus.BLOCKED): TransitionRule(
        AllowedActorCategory.OWNER,
        True,
        False,
    ),
    (TicketStatus.IN_PROGRESS, TicketStatus.BLOCKED): TransitionRule(
        AllowedActorCategory.OWNER,
        True,
        False,
    ),
    (TicketStatus.BLOCKED, TicketStatus.IN_PROGRESS): TransitionRule(
        AllowedActorCategory.OWNER,
        False,
        False,
    ),
    (TicketStatus.IN_PROGRESS, TicketStatus.DONE): TransitionRule(
        AllowedActorCategory.OWNER,
        False,
        False,
    ),
}

CANCELLATION_RULE = TransitionRule(
    allowed_actor=AllowedActorCategory.PM,
    reason_required=True,
    pm_override_required=True,
)
CANCELLABLE_FROM: set[TicketStatus] = {
    TicketStatus.TODO,
    TicketStatus.IN_PROGRESS,
    TicketStatus.BLOCKED,
    TicketStatus.IN_QA,
    TicketStatus.QA_FAILED,
}
TERMINAL_STATES: set[TicketStatus] = {TicketStatus.DONE, TicketStatus.CANCELLED}


def _is_reason_provided(reason: str | None) -> bool:
    return reason is not None and reason.strip() != ""


async def validate_transition(
    session: AsyncSession,
    *,
    ticket: Ticket | None,
    to_status: TicketStatus,
    actor: Actor,
    pm_override: bool,
    reason: str | None,
) -> None:
    """Validate a status transition and raise a domain error if invalid."""
    from_status = TicketStatus(ticket.status) if ticket is not None else None
    ticket_kind = TicketKind(ticket.ticket_kind) if ticket is not None else TicketKind.STANDARD

    if from_status in TERMINAL_STATES:
        raise InvalidTransitionError(
            from_status=from_status.value,
            to_status=to_status.value,
        )

    if to_status == TicketStatus.CANCELLED:
        if from_status not in CANCELLABLE_FROM:
            raise InvalidTransitionError(
                from_status=from_status.value if from_status is not None else None,
                to_status=to_status.value,
            )
        rule = CANCELLATION_RULE
    else:
        rules = TEST_ONLY_TRANSITION_RULES if ticket_kind == TicketKind.TEST_ONLY else TRANSITION_RULES
        transition_rule = rules.get((from_status, to_status))
        if transition_rule is None:
            raise InvalidTransitionError(
                from_status=from_status.value if from_status is not None else None,
                to_status=to_status.value,
            )
        rule = transition_rule

    if not await _actor_matches_category(session, ticket, actor, rule.allowed_actor):
        from_label = from_status.value if from_status is not None else "creation"
        raise ActorNotPermittedError(
            actor=actor.raw,
            action=f"transition from {from_label} to {to_status.value}",
        )

    if pm_override and actor.kind != ActorKind.HUMAN:
        raise OverrideNotPermittedError(actor=actor.raw)

    if rule.pm_override_required and not pm_override:
        raise OverrideNotPermittedError(actor=actor.raw)

    if rule.reason_required and not _is_reason_provided(reason):
        from_label = from_status.value if from_status is not None else "creation"
        raise ReasonRequiredError(transition=f"{from_label} -> {to_status.value}")


async def _actor_matches_category(
    session: AsyncSession,
    ticket: Ticket | None,
    actor: Actor,
    category: AllowedActorCategory,
) -> bool:
    if category == AllowedActorCategory.PM:
        return actor.kind == ActorKind.HUMAN

    if category == AllowedActorCategory.OWNER:
        if ticket is None or actor.kind != ActorKind.AGENT:
            return False
        return ticket.owner_agent_id == actor.id

    if category == AllowedActorCategory.ROLE_QA:
        if actor.kind != ActorKind.AGENT:
            return False
        agent = await session.get(Agent, actor.id)
        return agent is not None and agent.role == "qa"

    return False
