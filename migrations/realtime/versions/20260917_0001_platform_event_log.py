"""Лог PlatformEvent bus.

Revision ID: realtime_0001
Revises:
Create Date: 2026-09-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "realtime_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "platform_event_log",
        sa.Column("event_id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("company_id", sa.String(100), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("meta", postgresql.JSONB(), nullable=False),
        sa.Column("delivery", postgresql.JSONB(), nullable=True),
        sa.Column("processing_state", sa.String(32), nullable=False),
        sa.Column("owner_service", sa.String(64), nullable=True),
        sa.Column("causation_id", sa.String(64), nullable=True),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_platform_event_log_type", "platform_event_log", ["type"])
    op.create_index("ix_platform_event_log_causation", "platform_event_log", ["causation_id"])
    op.create_index(
        "ix_platform_event_log_deadline",
        "platform_event_log",
        ["deadline_at", "processing_state"],
    )
    op.create_index(
        "ix_platform_event_log_company_created",
        "platform_event_log",
        ["company_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_platform_event_log_company_created", table_name="platform_event_log")
    op.drop_index("ix_platform_event_log_deadline", table_name="platform_event_log")
    op.drop_index("ix_platform_event_log_causation", table_name="platform_event_log")
    op.drop_index("ix_platform_event_log_type", table_name="platform_event_log")
    op.drop_table("platform_event_log")
