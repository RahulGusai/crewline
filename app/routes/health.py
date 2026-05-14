"""Health check endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session

router = APIRouter()


@router.get("/healthz", tags=["health"])
async def healthz(session: Annotated[AsyncSession, Depends(get_session)]) -> dict[str, str]:
    """Liveness + DB connectivity check."""
    await session.execute(text("SELECT 1"))
    return {"status": "ok"}
