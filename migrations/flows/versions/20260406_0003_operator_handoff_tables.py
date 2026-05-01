"""operator_queues, operator_queue_members, operator_tasks

Revision ID: agents_0003
Revises: agents_0002
Create Date: 2026-04-06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "agents_0003"
down_revision: Union[str, None] = "agents_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "operator_queues",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("company_id", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=2048), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "slug", name="uq_operator_queues_company_slug"),
    )
    op.create_index("ix_operator_queues_company_id", "operator_queues", ["company_id"])

    op.create_table(
        "operator_queue_members",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("queue_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["queue_id"], ["operator_queues.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("queue_id", "user_id", name="uq_operator_queue_members_queue_user"),
    )
    op.create_index("ix_operator_queue_members_queue_id", "operator_queue_members", ["queue_id"])
    op.create_index("ix_operator_queue_members_user_id", "operator_queue_members", ["user_id"])

    op.create_table(
        "operator_tasks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("company_id", sa.String(length=255), nullable=False),
        sa.Column("queue_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=512), nullable=False),
        sa.Column("end_user_id", sa.String(length=255), nullable=False),
        sa.Column("flow_id", sa.String(length=255), nullable=False),
        sa.Column("branch_id", sa.String(length=255), nullable=False),
        sa.Column("a2a_task_id", sa.String(length=255), nullable=True),
        sa.Column("context_id", sa.String(length=255), nullable=True),
        sa.Column("correlation_id", sa.String(length=36), nullable=True),
        sa.Column("interrupt_snapshot", postgresql.JSONB(), nullable=True),
        sa.Column("claimed_by_user_id", sa.String(length=255), nullable=True),
        sa.Column("resolution_payload", postgresql.JSONB(), nullable=True),
        sa.Column("context_data_snapshot", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["queue_id"], ["operator_queues.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "correlation_id", name="uq_operator_tasks_company_correlation"),
    )
    op.create_index("ix_operator_tasks_company_id", "operator_tasks", ["company_id"])
    op.create_index("ix_operator_tasks_queue_id", "operator_tasks", ["queue_id"])
    op.create_index("ix_operator_tasks_status", "operator_tasks", ["status"])
    op.create_index("ix_operator_tasks_session_id", "operator_tasks", ["session_id"])
    op.create_index("ix_operator_tasks_flow_id", "operator_tasks", ["flow_id"])
    op.create_index("ix_operator_tasks_correlation_id", "operator_tasks", ["correlation_id"])
    op.create_index("ix_operator_tasks_queue_status", "operator_tasks", ["queue_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_operator_tasks_queue_status", table_name="operator_tasks")
    op.drop_index("ix_operator_tasks_correlation_id", table_name="operator_tasks")
    op.drop_index("ix_operator_tasks_flow_id", table_name="operator_tasks")
    op.drop_index("ix_operator_tasks_session_id", table_name="operator_tasks")
    op.drop_index("ix_operator_tasks_status", table_name="operator_tasks")
    op.drop_index("ix_operator_tasks_queue_id", table_name="operator_tasks")
    op.drop_index("ix_operator_tasks_company_id", table_name="operator_tasks")
    op.drop_table("operator_tasks")
    op.drop_index("ix_operator_queue_members_user_id", table_name="operator_queue_members")
    op.drop_index("ix_operator_queue_members_queue_id", table_name="operator_queue_members")
    op.drop_table("operator_queue_members")
    op.drop_index("ix_operator_queues_company_id", table_name="operator_queues")
    op.drop_table("operator_queues")
