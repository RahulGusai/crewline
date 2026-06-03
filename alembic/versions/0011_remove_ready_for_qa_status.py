"""Remove READY_FOR_QA ticket status.

Revision ID: 0011
Revises: 0010
Create Date: 2026-06-03 00:00:02.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(sa.text("UPDATE tickets SET status = 'IN_QA' WHERE status = 'READY_FOR_QA'"))


def downgrade() -> None:
    # READY_FOR_QA was a transient handoff status. Downgrade leaves normalized
    # ticket rows in IN_QA because there is no durable signal to restore.
    pass
