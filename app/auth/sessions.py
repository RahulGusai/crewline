"""Server-side session management."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.session import Session


def _generate_id() -> str:
    return secrets.token_urlsafe(32)


def _generate_csrf() -> str:
    return secrets.token_urlsafe(32)


async def create_session(db: AsyncSession, user_id: UUID) -> Session:
    """Create a new session for a user."""
    session = Session(
        id=_generate_id(),
        user_id=user_id,
        csrf_token=_generate_csrf(),
    )
    db.add(session)
    await db.flush()
    return session


async def lookup_session(db: AsyncSession, session_id: str) -> Session | None:
    """Return a live session and bump sliding expiry metadata."""
    settings = get_settings()
    cutoff = datetime.now(UTC) - timedelta(hours=settings.session_lifetime_hours)

    result = await db.execute(select(Session).where(Session.id == session_id))
    session = result.scalar_one_or_none()
    if session is None or session.revoked_at is not None:
        return None
    if session.last_seen_at < cutoff:
        await db.delete(session)
        await db.flush()
        return None

    session.last_seen_at = datetime.now(UTC)
    await db.flush()
    return session


async def revoke_session(db: AsyncSession, session_id: str) -> None:
    """Mark a session as revoked. Idempotent."""
    await db.execute(
        update(Session)
        .where(Session.id == session_id)
        .values(revoked_at=datetime.now(UTC))
    )
    await db.flush()


async def cleanup_expired_sessions(db: AsyncSession) -> int:
    """Delete sessions older than the configured lifetime."""
    settings = get_settings()
    cutoff = datetime.now(UTC) - timedelta(hours=settings.session_lifetime_hours)
    count_result = await db.execute(
        select(func.count()).select_from(Session).where(Session.last_seen_at < cutoff)
    )
    deleted_count = int(count_result.scalar_one())
    await db.execute(delete(Session).where(Session.last_seen_at < cutoff))
    await db.flush()
    return deleted_count
