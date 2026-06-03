"""Actor string parsing and validation."""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.exceptions import InvalidActorError
from app.enums import ActorKind, AgentId

PM_USER_ID = "00000000-0000-0000-0000-000000000001"
PM_HUMAN_IDS = {"pm", PM_USER_ID}


@dataclass(frozen=True)
class Actor:
    kind: ActorKind
    id: str
    raw: str

    @property
    def agent_id(self) -> AgentId | None:
        """If this is an agent actor, return the AgentId; otherwise None."""
        if self.kind != ActorKind.AGENT:
            return None
        try:
            return AgentId(self.id)
        except ValueError:
            return None


def parse_actor(actor_str: str) -> Actor:
    """Parse a `<kind>:<id>` actor string."""
    if not isinstance(actor_str, str) or ":" not in actor_str:
        raise InvalidActorError(actor=actor_str, reason="malformed")

    kind_str, _, id_str = actor_str.partition(":")
    if not kind_str or not id_str:
        raise InvalidActorError(actor=actor_str, reason="empty kind or id")

    try:
        kind = ActorKind(kind_str)
    except ValueError as exc:
        raise InvalidActorError(actor=actor_str, reason=f"unknown kind: {kind_str}") from exc

    if kind == ActorKind.AGENT:
        try:
            AgentId(id_str)
        except ValueError as exc:
            raise InvalidActorError(
                actor=actor_str,
                reason=f"unknown agent id: {id_str}",
            ) from exc

    if kind == ActorKind.HUMAN and id_str not in PM_HUMAN_IDS:
        raise InvalidActorError(
            actor=actor_str,
            reason=f"unknown human id (only PM is supported in v0): {id_str}",
        )

    if kind == ActorKind.SYSTEM and id_str not in {"system", "auto_qa_transition"}:
        raise InvalidActorError(
            actor=actor_str,
            reason=f"unknown system id (only 'system' supported): {id_str}",
        )

    return Actor(kind=kind, id=id_str, raw=actor_str)
