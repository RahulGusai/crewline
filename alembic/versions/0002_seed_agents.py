"""Seed the four required agents - Cortex, Lumen, Atlas, Sentinel.

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-01 00:00:01.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


AGENTS = [
    {"id": "cortex", "display_name": "Cortex", "role": "be"},
    {"id": "lumen", "display_name": "Lumen", "role": "fe"},
    {"id": "architect", "display_name": "Atlas", "role": "architect"},
    {"id": "sentinel", "display_name": "Sentinel", "role": "qa"},
]


def upgrade() -> None:
    for agent in AGENTS:
        op.execute(
            sa.text(
                "INSERT INTO agents (id, display_name, role, active) "
                "VALUES (:id, :display_name, :role, true) "
                "ON CONFLICT (id) DO NOTHING"
            ).bindparams(**agent)
        )


def downgrade() -> None:
    for agent in AGENTS:
        op.execute(sa.text("DELETE FROM agents WHERE id = :id").bindparams(id=agent["id"]))
