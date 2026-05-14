"""Generic pagination wrapper for list responses."""

from __future__ import annotations

from pydantic import BaseModel


class Paginated[T](BaseModel):
    items: list[T]
    limit: int
    offset: int
    has_more: bool
