"""Add ticket kind.

Revision ID: 0012
Revises: 0011
Create Date: 2026-06-10 00:00:01.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tickets",
        sa.Column("ticket_kind", sa.String(), nullable=False, server_default="STANDARD"),
    )


def downgrade() -> None:
    op.drop_column("tickets", "ticket_kind")
