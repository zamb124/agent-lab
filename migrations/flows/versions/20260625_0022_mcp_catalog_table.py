"""Revision ID: 20260625_0022
Revises: 20260622_0021
Create Date: 2026-06-25
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260625_0022"
down_revision: Union[str, None] = "20260622_0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mcp_catalog",
        sa.Column("key", sa.String(), primary_key=True, nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("key", name="uq_mcp_catalog_key"),
    )
    op.create_index("ix_mcp_catalog_expired_at", "mcp_catalog", ["expired_at"])
    op.create_index("ix_mcp_catalog_key", "mcp_catalog", ["key"])
    op.create_index("ix_mcp_catalog_key_prefix", "mcp_catalog", ["key"])
    op.create_index("ix_mcp_catalog_updated_at", "mcp_catalog", ["updated_at"])


def downgrade() -> None:
    op.drop_index("ix_mcp_catalog_updated_at", table_name="mcp_catalog")
    op.drop_index("ix_mcp_catalog_key_prefix", table_name="mcp_catalog")
    op.drop_index("ix_mcp_catalog_key", table_name="mcp_catalog")
    op.drop_index("ix_mcp_catalog_expired_at", table_name="mcp_catalog")
    op.drop_table("mcp_catalog")
