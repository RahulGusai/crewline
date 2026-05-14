"""Shared base schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class BaseSchema(BaseModel):
    """Read schemas - permissive, accepts ORM attributes."""

    model_config = ConfigDict(from_attributes=True)


class StrictSchema(BaseModel):
    """Input schemas - reject unknown fields."""

    model_config = ConfigDict(extra="forbid")

