"""Pydantic schemas for auth endpoints."""

from __future__ import annotations

from uuid import UUID

from app.schemas.common import BaseSchema, StrictSchema


class LoginRequest(StrictSchema):
    email: str
    password: str


class MeResponse(BaseSchema):
    user_id: UUID
    display_name: str
    email: str
    csrf_token: str
