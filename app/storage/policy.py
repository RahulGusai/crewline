"""File type policy for attachments."""

from __future__ import annotations

ALLOWED_CONTENT_TYPES: frozenset[str] = frozenset(
    {
        "image/png",
        "image/jpeg",
        "image/gif",
        "image/webp",
        "image/svg+xml",
        "application/pdf",
        "text/plain",
        "text/csv",
        "text/markdown",
        "application/json",
        "application/xml",
        "text/xml",
        "application/zip",
        "application/x-tar",
        "application/gzip",
        "application/x-gzip",
        "text/x-python",
        "text/javascript",
        "text/html",
        "text/css",
        "text/x-log",
    }
)


def is_content_type_allowed(content_type: str) -> bool:
    """Case-insensitive check against the whitelist."""
    return content_type.lower() in ALLOWED_CONTENT_TYPES
