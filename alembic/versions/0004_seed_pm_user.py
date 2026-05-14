"""Seed the PM user with an initial password.

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-04 00:00:01.000000

"""

import uuid
from collections.abc import Sequence

import bcrypt
import sqlalchemy as sa

from alembic import op
from app.config import get_settings

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PM_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
PM_EMAIL = "pm@crewline.local"
PM_DISPLAY_NAME = "PM"


def upgrade() -> None:
    bind = op.get_bind()

    existing = bind.execute(
        sa.text("SELECT id FROM users WHERE id = :id"),
        {"id": str(PM_USER_ID)},
    ).first()
    if existing is None:
        bind.execute(
            sa.text(
                "INSERT INTO users (id, email, display_name) "
                "VALUES (:id, :email, :name)"
            ),
            {
                "id": str(PM_USER_ID),
                "email": PM_EMAIL,
                "name": PM_DISPLAY_NAME,
            },
        )

    existing_cred = bind.execute(
        sa.text(
            "SELECT id FROM user_credentials "
            "WHERE user_id = :user_id AND type = 'password'"
        ),
        {"user_id": str(PM_USER_ID)},
    ).first()
    if existing_cred is not None:
        return

    password = get_settings().pm_initial_password
    if not password:
        raise RuntimeError("PM_INITIAL_PASSWORD env var is required for migration 0004.")

    password_hash = bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(rounds=12),
    ).decode("utf-8")
    bind.execute(
        sa.text(
            "INSERT INTO user_credentials (id, user_id, type, password_hash) "
            "VALUES (:id, :user_id, 'password', :hash)"
        ),
        {
            "id": str(uuid.uuid4()),
            "user_id": str(PM_USER_ID),
            "hash": password_hash,
        },
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text("DELETE FROM user_credentials WHERE user_id = :uid"),
        {"uid": str(PM_USER_ID)},
    )
    bind.execute(
        sa.text("DELETE FROM users WHERE id = :uid"),
        {"uid": str(PM_USER_ID)},
    )
