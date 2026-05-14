"""Authorization helpers for authenticated actors."""

from __future__ import annotations

from app.domain.actor import Actor
from app.domain.exceptions import ActorNotPermittedError
from app.enums import ActorKind
from app.models.ticket import Ticket


def require_pm(actor: Actor, action: str) -> None:
    """Raise if actor is not the PM."""
    if actor.kind != ActorKind.HUMAN:
        raise ActorNotPermittedError(actor=actor.raw, action=action)


def require_owned_ticket(actor: Actor, ticket: Ticket, action: str) -> None:
    """Agents may only operate on tickets they own."""
    if actor.kind == ActorKind.AGENT and ticket.owner_agent_id != actor.id:
        raise ActorNotPermittedError(actor=actor.raw, action=action)
