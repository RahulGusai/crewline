"""Pydantic schemas for ticket inputs and outputs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field, field_validator

from app.enums import TestSidecar, TicketKind, TicketStatus
from app.schemas.common import BaseSchema, StrictSchema

TEST_SIDECARS_METADATA_KEY = "test_sidecars"


def _validate_test_sidecars(metadata: dict[str, Any]) -> dict[str, Any]:
    """Validate the reserved ``test_sidecars`` metadata key against the allowlist.

    Other metadata keys stay free-form. The key is not frozen after creation:
    sidecars are resolved once by the agent process at runtime spawn, so edits
    before assignment are useful and edits mid-run have no effect.
    """
    if TEST_SIDECARS_METADATA_KEY not in metadata:
        return metadata
    raw = metadata[TEST_SIDECARS_METADATA_KEY]
    if not isinstance(raw, list):
        raise ValueError(f"{TEST_SIDECARS_METADATA_KEY} must be a list of sidecar names")
    normalized: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            raise ValueError(f"{TEST_SIDECARS_METADATA_KEY} entries must be strings")
        try:
            sidecar = TestSidecar(item)
        except ValueError:
            allowed = ", ".join(member.value for member in TestSidecar)
            raise ValueError(
                f"{TEST_SIDECARS_METADATA_KEY} entry {item!r} is not a known sidecar; allowed: {allowed}"
            ) from None
        if sidecar.value not in normalized:
            normalized.append(sidecar.value)
    metadata[TEST_SIDECARS_METADATA_KEY] = normalized
    return metadata


class TicketCreate(StrictSchema):
    title: str
    description: str | None = None
    repo_full_name: str
    related_repo_full_names: list[str] = Field(default_factory=list)
    owner_agent_id: str | None = None
    ticket_kind: TicketKind = TicketKind.STANDARD
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def _check_test_sidecars(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _validate_test_sidecars(value)


class TicketUpdate(StrictSchema):
    title: str | None = None
    description: str | None = None
    related_repo_full_names: list[str] | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("metadata")
    @classmethod
    def _check_test_sidecars(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is None:
            return None
        return _validate_test_sidecars(value)


class TicketPrUrlUpdate(StrictSchema):
    pr_url: str


class TicketTransition(StrictSchema):
    to_status: TicketStatus
    reason: str | None = None
    pm_override: bool = False


class TicketAssign(StrictSchema):
    new_owner_agent_id: str
    reason: str | None = None


class TicketRead(BaseSchema):
    id: int
    title: str
    description: str | None
    status: TicketStatus
    ticket_kind: TicketKind
    owner_agent_id: str | None
    repo_full_name: str
    related_repo_full_names: list[str]
    pr_url: str | None
    created_by: str
    created_at: datetime
    updated_at: datetime
    metadata_: dict[str, Any] = Field(serialization_alias="metadata")


class TicketMetricsRead(BaseSchema):
    ticket_id: int
    started_at: datetime | None
    completed_at: datetime | None
    total_elapsed_seconds: int | None
    blocked_seconds: int
    blocked_episodes: int
