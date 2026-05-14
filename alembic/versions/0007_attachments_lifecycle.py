"""Add lifecycle columns to ticket_attachments.

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-04 00:00:04.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("ticket_attachments", "url", new_column_name="s3_key")
    op.alter_column("ticket_attachments", "uploaded_at", nullable=True, server_default=None)
    op.add_column(
        "ticket_attachments",
        sa.Column("uploaded_by", sa.String(), nullable=False, server_default="system:system"),
    )
    op.add_column(
        "ticket_attachments",
        sa.Column("status", sa.String(), nullable=False, server_default="ready"),
    )
    op.add_column(
        "ticket_attachments",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.add_column(
        "ticket_attachments",
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "ticket_attachments",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE ticket_attachments "
        "SET finalized_at = uploaded_at, "
        "created_at = COALESCE(uploaded_at, created_at), "
        "content_type = COALESCE(content_type, 'application/octet-stream'), "
        "size_bytes = COALESCE(size_bytes, 0) "
        "WHERE finalized_at IS NULL"
    )
    op.alter_column("ticket_attachments", "uploaded_by", server_default=None)
    op.alter_column("ticket_attachments", "status", server_default=None)
    op.alter_column("ticket_attachments", "content_type", nullable=False)
    op.alter_column("ticket_attachments", "size_bytes", nullable=False)
    op.create_unique_constraint(
        "uq_ticket_attachments_s3_key",
        "ticket_attachments",
        ["s3_key"],
    )
    op.create_index(
        "ix_ticket_attachments_status_created_at",
        "ticket_attachments",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_ticket_attachments_ticket_id_deleted_at",
        "ticket_attachments",
        ["ticket_id", "deleted_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_ticket_attachments_ticket_id_deleted_at", table_name="ticket_attachments")
    op.drop_index("ix_ticket_attachments_status_created_at", table_name="ticket_attachments")
    op.drop_constraint(
        "uq_ticket_attachments_s3_key",
        "ticket_attachments",
        type_="unique",
    )
    op.alter_column("ticket_attachments", "size_bytes", nullable=True)
    op.alter_column("ticket_attachments", "content_type", nullable=True)
    op.drop_column("ticket_attachments", "deleted_at")
    op.drop_column("ticket_attachments", "finalized_at")
    op.drop_column("ticket_attachments", "created_at")
    op.drop_column("ticket_attachments", "status")
    op.drop_column("ticket_attachments", "uploaded_by")
    op.alter_column(
        "ticket_attachments",
        "uploaded_at",
        nullable=False,
        server_default=sa.text("now()"),
    )
    op.alter_column("ticket_attachments", "s3_key", new_column_name="url")
