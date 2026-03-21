"""KV storage + mcp_servers для agents БД

Revision ID: agents_0002
Revises: agents_0001
Create Date: 2026-03-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "agents_0002"
down_revision: Union[str, None] = "agents_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "storage",
        sa.Column("key", sa.String(), primary_key=True, nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("key", name="uq_storage_key"),
    )
    op.create_index("ix_storage_key_prefix", "storage", ["key"])
    op.create_index("ix_storage_updated_at", "storage", ["updated_at"])
    op.create_index("ix_storage_expired_at", "storage", ["expired_at"])

    op.create_table(
        "mcp_servers",
        sa.Column("key", sa.String(), primary_key=True, nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("key", name="uq_mcp_servers_key"),
    )
    op.create_index("ix_mcp_servers_expired_at", "mcp_servers", ["expired_at"])
    op.create_index("ix_mcp_servers_key", "mcp_servers", ["key"])
    op.create_index("ix_mcp_servers_key_prefix", "mcp_servers", ["key"])
    op.create_index("ix_mcp_servers_updated_at", "mcp_servers", ["updated_at"])


def downgrade() -> None:
    op.drop_index("ix_mcp_servers_updated_at", table_name="mcp_servers")
    op.drop_index("ix_mcp_servers_key_prefix", table_name="mcp_servers")
    op.drop_index("ix_mcp_servers_key", table_name="mcp_servers")
    op.drop_index("ix_mcp_servers_expired_at", table_name="mcp_servers")
    op.drop_table("mcp_servers")

    op.drop_index("ix_storage_expired_at", table_name="storage")
    op.drop_index("ix_storage_updated_at", table_name="storage")
    op.drop_index("ix_storage_key_prefix", table_name="storage")
    op.drop_table("storage")
