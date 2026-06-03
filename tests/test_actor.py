"""Unit tests for actor parsing."""

import pytest

from app.domain.actor import parse_actor
from app.domain.exceptions import InvalidActorError
from app.enums import ActorKind, AgentId


@pytest.mark.parametrize(
    "actor, agent_id",
    [
        ("agent:cortex", AgentId.CORTEX),
        ("agent:lumen", AgentId.LUMEN),
        ("agent:architect", AgentId.ARCHITECT),
        ("agent:sentinel", AgentId.SENTINEL),
    ],
)
def test_parse_actor_accepts_agent_ids(actor: str, agent_id: AgentId) -> None:
    parsed = parse_actor(actor)

    assert parsed.kind == ActorKind.AGENT
    assert parsed.id == agent_id.value
    assert parsed.agent_id == agent_id


@pytest.mark.parametrize("actor", ["agent:be", "agent:fe", "agent:qa"])
def test_parse_actor_rejects_role_names_as_agent_ids(actor: str) -> None:
    with pytest.raises(InvalidActorError, match="unknown agent id"):
        parse_actor(actor)
