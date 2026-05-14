"""Error response shape used uniformly across the API."""

from __future__ import annotations

from typing import Any

from app.schemas.common import BaseSchema


class ErrorBody(BaseSchema):
    code: str
    message: str
    details: dict[str, Any]


class ErrorResponse(BaseSchema):
    error: ErrorBody

