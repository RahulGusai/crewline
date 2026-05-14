"""Authentication middleware for cookie sessions and agent API keys."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.auth.credentials import lookup_credential
from app.auth.csrf import CSRF_HEADER, validate_csrf
from app.auth.sessions import lookup_session
from app.config import get_settings
from app.db import session_scope

PUBLIC_PATHS: set[str] = {
    "/auth/login",
    "/github/callback",
    "/healthz",
    "/openapi.json",
    "/docs",
    "/docs/oauth2-redirect",
    "/redoc",
}

MUTATING_METHODS: set[str] = {"POST", "PATCH", "PUT", "DELETE"}


class AuthMiddleware(BaseHTTPMiddleware):
    """Resolve the request actor; route dependencies enforce permissions."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.method == "OPTIONS" or request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        auth_header = request.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            api_key = auth_header[7:].strip()
            actor = await self._authenticate_agent(api_key)
            if actor is None:
                return self._error(401, "invalid_api_key", "API key is invalid or revoked")
            request.state.actor_str = actor
            return await call_next(request)

        settings = get_settings()
        cookie_value = request.cookies.get(settings.cookie_name)
        if cookie_value:
            actor, csrf_expected = await self._authenticate_session(cookie_value)
            if actor is None:
                return self._error(401, "session_invalid", "Session is invalid or expired")

            if request.method in MUTATING_METHODS:
                presented = request.headers.get(CSRF_HEADER)
                if not validate_csrf(csrf_expected, presented):
                    return self._error(403, "csrf_invalid", "CSRF token missing or invalid")

            request.state.actor_str = actor
            return await call_next(request)

        return self._error(401, "not_authenticated", "Authentication required")

    async def _authenticate_agent(self, api_key: str) -> str | None:
        async with session_scope() as db:
            credential = await lookup_credential(db, api_key)
            if credential is None:
                return None
            return f"agent:{credential.agent_id}"

    async def _authenticate_session(self, cookie_value: str) -> tuple[str | None, str]:
        async with session_scope() as db:
            session = await lookup_session(db, cookie_value)
            if session is None:
                return (None, "")
            return (f"human:{session.user_id}", session.csrf_token)

    def _error(self, http_status: int, code: str, message: str) -> JSONResponse:
        return JSONResponse(
            status_code=http_status,
            content={
                "error": {
                    "code": code,
                    "message": message,
                    "details": {},
                }
            },
        )
