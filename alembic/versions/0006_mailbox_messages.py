"""Mailbox messages table.

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-04 00:00:03.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mailbox_messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("sender", sa.String(), nullable=False),
        sa.Column("recipient", sa.String(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("requires_response", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("correlation_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(
            ["correlation_id"],
            ["mailbox_messages.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "(acknowledged_at IS NULL) OR (rejected_at IS NULL)",
            name="ck_mailbox_messages_one_terminal_state",
        ),
    )
    op.create_index(
        "ix_mailbox_messages_recipient_created_at",
        "mailbox_messages",
        ["recipient", "created_at"],
    )
    op.create_index(
        "ix_mailbox_messages_pending",
        "mailbox_messages",
        ["recipient", "created_at"],
        postgresql_where=sa.text("acknowledged_at IS NULL AND rejected_at IS NULL"),
    )
    op.create_index(
        "ix_mailbox_messages_correlation_id",
        "mailbox_messages",
        ["correlation_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_mailbox_messages_correlation_id", table_name="mailbox_messages")
    op.drop_index("ix_mailbox_messages_pending", table_name="mailbox_messages")
    op.drop_index("ix_mailbox_messages_recipient_created_at", table_name="mailbox_messages")
    op.drop_table("mailbox_messages")
