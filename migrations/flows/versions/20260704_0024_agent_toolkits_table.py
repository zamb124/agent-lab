"""Revision ID: 20260704_0024
Revises: 20260625_0023
Create Date: 2026-07-04
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260704_0024"
down_revision: Union[str, None] = "20260625_0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_toolkits",
        sa.Column("key", sa.String(), primary_key=True, nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("key", name="uq_agent_toolkits_key"),
    )
    op.create_index("ix_agent_toolkits_expired_at", "agent_toolkits", ["expired_at"])
    op.create_index("ix_agent_toolkits_key", "agent_toolkits", ["key"])
    op.create_index("ix_agent_toolkits_key_prefix", "agent_toolkits", ["key"])
    op.create_index("ix_agent_toolkits_updated_at", "agent_toolkits", ["updated_at"])


def downgrade() -> None:
    op.drop_index("ix_agent_toolkits_updated_at", table_name="agent_toolkits")
    op.drop_index("ix_agent_toolkits_key_prefix", table_name="agent_toolkits")
    op.drop_index("ix_agent_toolkits_key", table_name="agent_toolkits")
    op.drop_index("ix_agent_toolkits_expired_at", table_name="agent_toolkits")
    op.drop_table("agent_toolkits")
