"""Seed initial API keys for the four agents.

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-04 00:00:02.000000

"""

import hashlib
import uuid
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.config import get_settings

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AGENTS_AND_SETTINGS = [
    ("cortex", "agent_be_initial_key"),
    ("lumen", "agent_fe_initial_key"),
    ("architect", "agent_architect_initial_key"),
    ("sentinel", "agent_qa_initial_key"),
]


def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def upgrade() -> None:
    bind = op.get_bind()
    settings = get_settings()

    for agent_id, setting_name in AGENTS_AND_SETTINGS:
        existing = bind.execute(
            sa.text(
                "SELECT id FROM agent_credentials "
                "WHERE agent_id = :aid AND revoked_at IS NULL "
                "LIMIT 1"
            ),
            {"aid": agent_id},
        ).first()
        if existing is not None:
            continue

        key = getattr(settings, setting_name)
        if not key:
            env_var = setting_name.upper()
            raise RuntimeError(f"{env_var} env var is required for migration 0005.")
        bind.execute(
            sa.text(
                "INSERT INTO agent_credentials (id, agent_id, api_key_hash, description) "
                "VALUES (:id, :aid, :hash, :desc)"
            ),
            {
                "id": str(uuid.uuid4()),
                "aid": agent_id,
                "hash": _hash_key(key),
                "desc": "Initial seed credential",
            },
        )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text("DELETE FROM agent_credentials WHERE description = 'Initial seed credential'")
    )
