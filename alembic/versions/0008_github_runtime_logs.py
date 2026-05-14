"""GitHub integration, ticket repo fields, and runtime logs.

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-14 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "github_installations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("pm_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("installation_id", sa.BigInteger(), nullable=False),
        sa.Column("account_login", sa.Text(), nullable=False),
        sa.Column("account_type", sa.Text(), nullable=False),
        sa.Column(
            "installed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), server_default="active", nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["pm_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("installation_id"),
    )
    op.create_index(
        "ix_github_installations_pm_user_id",
        "github_installations",
        ["pm_user_id"],
    )

    op.create_table(
        "github_installation_repos",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("installation_id", sa.BigInteger(), nullable=False),
        sa.Column("github_repo_id", sa.BigInteger(), nullable=False),
        sa.Column("repo_full_name", sa.Text(), nullable=False),
        sa.Column("default_branch", sa.Text(), server_default="main", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["installation_id"],
            ["github_installations.installation_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("installation_id", "github_repo_id"),
    )
    op.create_index(
        "ix_github_installation_repos_installation_id",
        "github_installation_repos",
        ["installation_id"],
    )

    op.create_table(
        "github_install_states",
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("pm_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("state"),
    )

    op.add_column("tickets", sa.Column("repo_full_name", sa.Text(), nullable=True))
    op.add_column(
        "tickets",
        sa.Column(
            "related_repo_full_names",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
    )
    op.add_column("tickets", sa.Column("pr_url", sa.Text(), nullable=True))
    op.add_column("tickets", sa.Column("qa_notes", sa.Text(), nullable=True))
    op.execute("UPDATE tickets SET repo_full_name = 'local/crewline' WHERE repo_full_name IS NULL")
    op.alter_column("tickets", "repo_full_name", nullable=False)

    op.create_table(
        "runtime_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ticket_id", sa.BigInteger(), nullable=False),
        sa.Column("agent_id", sa.Text(), nullable=False),
        sa.Column("runtime_type", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("total_turns", sa.Integer(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("classification", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_runtime_logs_ticket_created", "runtime_logs", ["ticket_id", "created_at"])
    op.create_index("ix_runtime_logs_ticket_agent", "runtime_logs", ["ticket_id", "agent_id"])


def downgrade() -> None:
    op.drop_index("ix_runtime_logs_ticket_agent", table_name="runtime_logs")
    op.drop_index("ix_runtime_logs_ticket_created", table_name="runtime_logs")
    op.drop_table("runtime_logs")
    op.drop_column("tickets", "qa_notes")
    op.drop_column("tickets", "pr_url")
    op.drop_column("tickets", "related_repo_full_names")
    op.drop_column("tickets", "repo_full_name")
    op.drop_table("github_install_states")
    op.drop_index(
        "ix_github_installation_repos_installation_id",
        table_name="github_installation_repos",
    )
    op.drop_table("github_installation_repos")
    op.drop_index("ix_github_installations_pm_user_id", table_name="github_installations")
    op.drop_table("github_installations")
