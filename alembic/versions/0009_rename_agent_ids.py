"""Rename agent ids to canonical agent names.

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-18 00:00:01.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            CREATE TEMPORARY TABLE agent_id_map (
                old_id text PRIMARY KEY,
                new_id text NOT NULL,
                old_actor text NOT NULL,
                new_actor text NOT NULL,
                display_name text NOT NULL
            ) ON COMMIT DROP
            """
        )
    )
    bind.execute(
        sa.text(
            """
            INSERT INTO agent_id_map (old_id, new_id, old_actor, new_actor, display_name)
            VALUES
                ('be', 'cortex', 'agent:be', 'agent:cortex', 'Cortex'),
                ('fe', 'lumen', 'agent:fe', 'agent:lumen', 'Lumen'),
                ('qa', 'sentinel', 'agent:qa', 'agent:sentinel', 'Sentinel')
            """
        )
    )

    bind.execute(
        sa.text(
            """
            UPDATE agents AS a
            SET display_name = a.display_name || ' (legacy id: ' || a.id || ')'
            WHERE a.id IN (SELECT old_id FROM agent_id_map)
              AND EXISTS (SELECT 1 FROM agents existing WHERE existing.id = a.id)
              AND NOT EXISTS (SELECT 1 FROM agents existing WHERE existing.id IN (SELECT new_id FROM agent_id_map))
            """
        )
    )
    bind.execute(
        sa.text(
            """
            INSERT INTO agents (id, display_name, role, active, created_at)
            SELECT m.new_id, m.display_name, a.role, a.active, a.created_at
            FROM agents AS a
            JOIN agent_id_map AS m ON m.old_id = a.id
            ON CONFLICT (id) DO NOTHING
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE agent_credentials AS c
            SET agent_id = m.new_id
            FROM agent_id_map AS m
            WHERE c.agent_id = m.old_id
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE tickets AS t
            SET owner_agent_id = m.new_id
            FROM agent_id_map AS m
            WHERE t.owner_agent_id = m.old_id
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE ticket_audit_log AS l
            SET from_owner = m.new_id
            FROM agent_id_map AS m
            WHERE l.from_owner = m.old_id
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE ticket_audit_log AS l
            SET to_owner = m.new_id
            FROM agent_id_map AS m
            WHERE l.to_owner = m.old_id
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE ticket_artifacts AS a
            SET author = m.new_actor
            FROM agent_id_map AS m
            WHERE a.author = m.old_actor
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE mailbox_messages AS msg
            SET sender = m.new_actor
            FROM agent_id_map AS m
            WHERE msg.sender = m.old_actor
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE mailbox_messages AS msg
            SET recipient = m.new_actor
            FROM agent_id_map AS m
            WHERE msg.recipient = m.old_actor
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE runtime_logs AS r
            SET agent_id = m.new_id
            FROM agent_id_map AS m
            WHERE r.agent_id = m.old_id
            """
        )
    )
    bind.execute(
        sa.text(
            """
            DELETE FROM agents AS a
            USING agent_id_map AS m
            WHERE a.id = m.old_id
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            CREATE TEMPORARY TABLE agent_id_map (
                old_id text PRIMARY KEY,
                new_id text NOT NULL,
                old_actor text NOT NULL,
                new_actor text NOT NULL,
                display_name text NOT NULL
            ) ON COMMIT DROP
            """
        )
    )
    bind.execute(
        sa.text(
            """
            INSERT INTO agent_id_map (old_id, new_id, old_actor, new_actor, display_name)
            VALUES
                ('cortex', 'be', 'agent:cortex', 'agent:be', 'Cortex'),
                ('lumen', 'fe', 'agent:lumen', 'agent:fe', 'Lumen'),
                ('sentinel', 'qa', 'agent:sentinel', 'agent:qa', 'Sentinel')
            """
        )
    )

    bind.execute(
        sa.text(
            """
            UPDATE agents AS a
            SET display_name = a.display_name || ' (canonical id: ' || a.id || ')'
            WHERE a.id IN (SELECT old_id FROM agent_id_map)
              AND EXISTS (SELECT 1 FROM agents existing WHERE existing.id = a.id)
              AND NOT EXISTS (SELECT 1 FROM agents existing WHERE existing.id IN (SELECT new_id FROM agent_id_map))
            """
        )
    )
    bind.execute(
        sa.text(
            """
            INSERT INTO agents (id, display_name, role, active, created_at)
            SELECT m.new_id, m.display_name, a.role, a.active, a.created_at
            FROM agents AS a
            JOIN agent_id_map AS m ON m.old_id = a.id
            ON CONFLICT (id) DO NOTHING
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE agent_credentials AS c
            SET agent_id = m.new_id
            FROM agent_id_map AS m
            WHERE c.agent_id = m.old_id
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE tickets AS t
            SET owner_agent_id = m.new_id
            FROM agent_id_map AS m
            WHERE t.owner_agent_id = m.old_id
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE ticket_audit_log AS l
            SET from_owner = m.new_id
            FROM agent_id_map AS m
            WHERE l.from_owner = m.old_id
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE ticket_audit_log AS l
            SET to_owner = m.new_id
            FROM agent_id_map AS m
            WHERE l.to_owner = m.old_id
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE ticket_artifacts AS a
            SET author = m.new_actor
            FROM agent_id_map AS m
            WHERE a.author = m.old_actor
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE mailbox_messages AS msg
            SET sender = m.new_actor
            FROM agent_id_map AS m
            WHERE msg.sender = m.old_actor
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE mailbox_messages AS msg
            SET recipient = m.new_actor
            FROM agent_id_map AS m
            WHERE msg.recipient = m.old_actor
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE runtime_logs AS r
            SET agent_id = m.new_id
            FROM agent_id_map AS m
            WHERE r.agent_id = m.old_id
            """
        )
    )
    bind.execute(
        sa.text(
            """
            DELETE FROM agents AS a
            USING agent_id_map AS m
            WHERE a.id = m.old_id
            """
        )
    )
