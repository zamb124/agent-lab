"""Add scheduler tasks table

Revision ID: shared_0003
Revises: shared_0002
Create Date: 2026-03-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "shared_0003"
down_revision: Union[str, None] = "shared_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scheduler_tasks",
        sa.Column("id", sa.String(length=255), primary_key=True, nullable=False),
        sa.Column("company_id", sa.String(length=255), nullable=False),
        sa.Column("schedule_id", sa.String(length=255), nullable=True),
        sa.Column("target_service", sa.String(length=64), nullable=False),
        sa.Column("task_name", sa.String(length=255), nullable=False),
        sa.Column("queue_name", sa.String(length=128), nullable=True),
        sa.Column("schedule_type", sa.String(length=32), nullable=False),
        sa.Column("cron", sa.String(length=128), nullable=True),
        sa.Column("interval_seconds", sa.Integer(), nullable=True),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
    )

    op.create_index("ix_scheduler_tasks_id", "scheduler_tasks", ["id"])
    op.create_index("ix_scheduler_tasks_company_id", "scheduler_tasks", ["company_id"])
    op.create_index("ix_scheduler_tasks_schedule_id", "scheduler_tasks", ["schedule_id"])
    op.create_index("ix_scheduler_tasks_target_service", "scheduler_tasks", ["target_service"])
    op.create_index("ix_scheduler_tasks_task_name", "scheduler_tasks", ["task_name"])
    op.create_index("ix_scheduler_tasks_schedule_type", "scheduler_tasks", ["schedule_type"])
    op.create_index("ix_scheduler_tasks_status", "scheduler_tasks", ["status"])
    op.create_index("ix_scheduler_tasks_created_by_user_id", "scheduler_tasks", ["created_by_user_id"])
    op.create_index("ix_scheduler_tasks_next_run_at", "scheduler_tasks", ["next_run_at"])
    op.create_index("ix_scheduler_tasks_company_status", "scheduler_tasks", ["company_id", "status"])
    op.create_index("ix_scheduler_tasks_company_service", "scheduler_tasks", ["company_id", "target_service"])
    op.create_index("ix_scheduler_tasks_company_task", "scheduler_tasks", ["company_id", "task_name"])
    op.create_index("ix_scheduler_tasks_company_next_run", "scheduler_tasks", ["company_id", "next_run_at"])


def downgrade() -> None:
    op.drop_table("scheduler_tasks")
