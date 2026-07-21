"""Revision ID: 20260721_0026
Revises: 20260714_0025
Create Date: 2026-07-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260721_0026"
down_revision: Union[str, None] = "20260714_0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tool_tag_groups",
        sa.Column("key", sa.String(), primary_key=True, nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("key", name="uq_tool_tag_groups_key"),
    )
    op.create_index("ix_tool_tag_groups_expired_at", "tool_tag_groups", ["expired_at"])
    op.create_index("ix_tool_tag_groups_key", "tool_tag_groups", ["key"])
    op.create_index("ix_tool_tag_groups_key_prefix", "tool_tag_groups", ["key"])
    op.create_index("ix_tool_tag_groups_updated_at", "tool_tag_groups", ["updated_at"])


def downgrade() -> None:
    op.drop_index("ix_tool_tag_groups_updated_at", table_name="tool_tag_groups")
    op.drop_index("ix_tool_tag_groups_key_prefix", table_name="tool_tag_groups")
    op.drop_index("ix_tool_tag_groups_key", table_name="tool_tag_groups")
    op.drop_index("ix_tool_tag_groups_expired_at", table_name="tool_tag_groups")
    op.drop_table("tool_tag_groups")
