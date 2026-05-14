"""Authentication routes: login, logout, and me."""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.passwords import DUMMY_HASH, verify_password
from app.auth.sessions import create_session, lookup_session, revoke_session
from app.config import get_settings
from app.db import get_session
from app.models.user import User
from app.models.user_credential import UserCredential
from app.schemas.auth import LoginRequest, MeResponse

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", status_code=status.HTTP_204_NO_CONTENT)
async def login_route(
    payload: LoginRequest,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    settings = get_settings()

    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    credential: UserCredential | None = None
    if user is not None:
        credential_result = await db.execute(
            select(UserCredential).where(
                UserCredential.user_id == user.id,
                UserCredential.type == "password",
            )
        )
        credential = credential_result.scalar_one_or_none()

    password_hash = (
        credential.password_hash
        if credential is not None and credential.password_hash is not None
        else DUMMY_HASH
    )
    is_valid = verify_password(payload.password, password_hash)
    if user is None or credential is None or not is_valid:
        logger.warning("auth.login_failed", email=payload.email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    session = await create_session(db, user.id)
    response.set_cookie(
        key=settings.cookie_name,
        value=session.id,
        max_age=settings.session_lifetime_hours * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/",
    )
    logger.info("auth.login_success", user_id=str(user.id))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout_route(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    settings = get_settings()
    cookie_value = request.cookies.get(settings.cookie_name)
    if cookie_value:
        await revoke_session(db, cookie_value)
    response.delete_cookie(
        key=settings.cookie_name,
        path="/",
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
    )
    logger.info("auth.logout")


@router.get("/me", response_model=MeResponse)
async def me_route(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_session)],
) -> MeResponse:
    settings = get_settings()
    cookie_value = request.cookies.get(settings.cookie_name)
    if not cookie_value:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No session",
        )

    session = await lookup_session(db, cookie_value)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session",
        )

    user_result = await db.execute(select(User).where(User.id == session.user_id))
    user = user_result.scalar_one()
    return MeResponse(
        user_id=user.id,
        display_name=user.display_name,
        email=user.email,
        csrf_token=session.csrf_token,
    )
