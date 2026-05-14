"""CSRF token validation."""

from __future__ import annotations

import secrets

CSRF_HEADER = "X-CSRF-Token"


def validate_csrf(expected: str, presented: str | None) -> bool:
    """Constant-time CSRF comparison."""
    if presented is None:
        return False
    return secrets.compare_digest(expected, presented)
