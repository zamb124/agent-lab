"""Revision ID: 20260714_0025
Revises: 20260704_0024
Create Date: 2026-07-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260714_0025"
down_revision: Union[str, None] = "20260704_0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_skills",
        sa.Column("key", sa.String(), primary_key=True, nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("key", name="uq_agent_skills_key"),
    )
    op.create_index("ix_agent_skills_expired_at", "agent_skills", ["expired_at"])
    op.create_index("ix_agent_skills_key", "agent_skills", ["key"])
    op.create_index("ix_agent_skills_key_prefix", "agent_skills", ["key"])
    op.create_index("ix_agent_skills_updated_at", "agent_skills", ["updated_at"])


def downgrade() -> None:
    op.drop_index("ix_agent_skills_updated_at", table_name="agent_skills")
    op.drop_index("ix_agent_skills_key_prefix", table_name="agent_skills")
    op.drop_index("ix_agent_skills_key", table_name="agent_skills")
    op.drop_index("ix_agent_skills_expired_at", table_name="agent_skills")
    op.drop_table("agent_skills")
