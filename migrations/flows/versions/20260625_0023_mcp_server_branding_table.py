"""Revision ID: 20260625_0023
Revises: 20260625_0022
Create Date: 2026-06-25
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260625_0023"
down_revision: Union[str, None] = "20260625_0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mcp_server_branding",
        sa.Column("key", sa.String(), primary_key=True, nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("key", name="uq_mcp_server_branding_key"),
    )
    op.create_index("ix_mcp_server_branding_expired_at", "mcp_server_branding", ["expired_at"])
    op.create_index("ix_mcp_server_branding_key", "mcp_server_branding", ["key"])
    op.create_index("ix_mcp_server_branding_key_prefix", "mcp_server_branding", ["key"])
    op.create_index("ix_mcp_server_branding_updated_at", "mcp_server_branding", ["updated_at"])


def downgrade() -> None:
    op.drop_index("ix_mcp_server_branding_updated_at", table_name="mcp_server_branding")
    op.drop_index("ix_mcp_server_branding_key_prefix", table_name="mcp_server_branding")
    op.drop_index("ix_mcp_server_branding_key", table_name="mcp_server_branding")
    op.drop_index("ix_mcp_server_branding_expired_at", table_name="mcp_server_branding")
    op.drop_table("mcp_server_branding")
