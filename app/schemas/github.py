"""Schemas for GitHub App integration endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from app.schemas.common import BaseSchema, StrictSchema


class GitHubRepo(BaseSchema):
    id: int
    full_name: str
    default_branch: str


class GitHubInstallationStatus(BaseSchema):
    connected: bool
    account_login: str | None = None
    account_type: Literal["User", "Organization"] | None = None
    installed_at: datetime | None = None
    repos: list[GitHubRepo] = []


class GitHubTokenRequest(StrictSchema):
    repo_full_name: str | None = None


class GitHubTokenResponse(BaseSchema):
    token: str
    expires_at: datetime
    clone_url: str
    repo_full_name: str


class MergePrResponse(BaseSchema):
    merged: bool
    sha: str | None = None
    message: str | None = None
    error_code: str | None = None
    error_message: str | None = None
