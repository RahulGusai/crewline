"""Agent API key validation."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_credential import AgentCredential


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


async def lookup_credential(
    db: AsyncSession,
    api_key: str,
) -> AgentCredential | None:
    """Return a live agent credential by API key and update last-used metadata."""
    key_hash = hash_api_key(api_key)
    result = await db.execute(
        select(AgentCredential).where(AgentCredential.api_key_hash == key_hash)
    )
    credential = result.scalar_one_or_none()
    if credential is None or credential.revoked_at is not None:
        return None

    credential.last_used_at = datetime.now(UTC)
    await db.flush()
    return credential
