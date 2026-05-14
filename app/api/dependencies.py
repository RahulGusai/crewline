"""FastAPI dependencies for shared concerns across routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from app.domain.actor import Actor, parse_actor
from app.domain.exceptions import ActorNotPermittedError
from app.enums import ActorKind


async def get_current_actor(request: Request) -> Actor:
    """Return the authenticated actor set by auth middleware."""
    actor_str = getattr(request.state, "actor_str", None)
    if actor_str is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return parse_actor(actor_str)


async def require_pm_actor(
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> Actor:
    """Return the actor only when it is the PM."""
    if actor.kind != ActorKind.HUMAN:
        raise ActorNotPermittedError(
            actor=actor.raw,
            action="this action requires PM authentication",
        )
    return actor
