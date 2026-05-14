"""Helpers for paginated list responses."""

from __future__ import annotations

from collections.abc import Sequence

from app.schemas.pagination import Paginated


def to_paginated[T](
    items: Sequence[T],
    *,
    limit: int,
    offset: int,
) -> Paginated[T]:
    """Wrap a sequence of items into a Paginated response."""
    return Paginated[T](
        items=list(items),
        limit=limit,
        offset=offset,
        has_more=len(items) == limit,
    )
