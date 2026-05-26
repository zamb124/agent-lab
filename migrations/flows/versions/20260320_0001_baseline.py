"""Baseline flows DB

Revision ID: agents_0001
Revises:
Create Date: 2026-03-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "agents_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "flows",
        sa.Column("key", sa.String(), primary_key=True, nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("key", name="uq_flows_key"),
    )
    op.create_index("ix_flows_key", "flows", ["key"])
    op.create_index("ix_flows_key_prefix", "flows", ["key"])
    op.create_index("ix_flows_updated_at", "flows", ["updated_at"])
    op.create_index("ix_flows_expired_at", "flows", ["expired_at"])

    op.create_table(
        "flows_versions",
        sa.Column("key", sa.String(), primary_key=True, nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("key", name="uq_flows_versions_key"),
    )
    op.create_index("ix_flows_versions_key", "flows_versions", ["key"])
    op.create_index("ix_flows_versions_key_prefix", "flows_versions", ["key"])
    op.create_index("ix_flows_versions_updated_at", "flows_versions", ["updated_at"])
    op.create_index("ix_flows_versions_expired_at", "flows_versions", ["expired_at"])

    op.create_table(
        "nodes",
        sa.Column("key", sa.String(), primary_key=True, nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("key", name="uq_nodes_key"),
    )
    op.create_index("ix_nodes_key", "nodes", ["key"])
    op.create_index("ix_nodes_key_prefix", "nodes", ["key"])
    op.create_index("ix_nodes_updated_at", "nodes", ["updated_at"])
    op.create_index("ix_nodes_expired_at", "nodes", ["expired_at"])

    op.create_table(
        "tools",
        sa.Column("key", sa.String(), primary_key=True, nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("key", name="uq_tools_key"),
    )
    op.create_index("ix_tools_key", "tools", ["key"])
    op.create_index("ix_tools_key_prefix", "tools", ["key"])
    op.create_index("ix_tools_updated_at", "tools", ["updated_at"])
    op.create_index("ix_tools_expired_at", "tools", ["expired_at"])

    op.create_table(
        "resources",
        sa.Column("key", sa.String(), primary_key=True, nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("key", name="uq_resources_key"),
    )
    op.create_index("ix_resources_key", "resources", ["key"])
    op.create_index("ix_resources_key_prefix", "resources", ["key"])
    op.create_index("ix_resources_updated_at", "resources", ["updated_at"])
    op.create_index("ix_resources_expired_at", "resources", ["expired_at"])

    op.create_table(
        "scheduled_tasks",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("schedule_id", sa.String(), nullable=True),
        sa.Column("flow_id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("schedule_type", sa.String(), nullable=False),
        sa.Column("content_type", sa.String(), nullable=False),
        sa.Column("cron", sa.String(), nullable=True),
        sa.Column("interval_minutes", sa.Integer(), nullable=True),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("content", sa.String(), nullable=False),
        sa.Column("tool_args", postgresql.JSONB(), nullable=True),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.String(), nullable=True),
    )
    op.create_index("ix_scheduled_tasks_session_id", "scheduled_tasks", ["session_id"])
    op.create_index("ix_scheduled_tasks_flow_id", "scheduled_tasks", ["flow_id"])
    op.create_index("ix_scheduled_tasks_status", "scheduled_tasks", ["status"])
    op.create_index("ix_scheduled_tasks_next_run", "scheduled_tasks", ["next_run"])


def downgrade() -> None:
    op.drop_table("scheduled_tasks")
    op.drop_table("resources")
    op.drop_table("tools")
    op.drop_table("nodes")
    op.drop_table("flows_versions")
    op.drop_table("flows")
