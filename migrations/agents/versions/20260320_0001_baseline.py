"""Baseline agents DB

Revision ID: agents_0001
Revises:
Create Date: 2026-03-20
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "agents_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agents",
        sa.Column("key", sa.String(), primary_key=True, nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("key", name="uq_agents_key"),
    )
    op.create_index("ix_agents_key", "agents", ["key"])
    op.create_index("ix_agents_key_prefix", "agents", ["key"])
    op.create_index("ix_agents_updated_at", "agents", ["updated_at"])
    op.create_index("ix_agents_expired_at", "agents", ["expired_at"])

    op.create_table(
        "agents_versions",
        sa.Column("key", sa.String(), primary_key=True, nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("key", name="uq_agents_versions_key"),
    )
    op.create_index("ix_agents_versions_key", "agents_versions", ["key"])
    op.create_index("ix_agents_versions_key_prefix", "agents_versions", ["key"])
    op.create_index("ix_agents_versions_updated_at", "agents_versions", ["updated_at"])
    op.create_index("ix_agents_versions_expired_at", "agents_versions", ["expired_at"])

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
        "states",
        sa.Column("key", sa.String(), primary_key=True, nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("key", name="uq_states_key"),
    )
    op.create_index("ix_states_key", "states", ["key"])
    op.create_index("ix_states_key_prefix", "states", ["key"])
    op.create_index("ix_states_updated_at", "states", ["updated_at"])
    op.create_index("ix_states_expired_at", "states", ["expired_at"])

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
        "evaluation_results",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("agent_id", sa.String(), nullable=False),
        sa.Column("skill_id", sa.String(), nullable=False),
        sa.Column("run_date", sa.Date(), nullable=False),
        sa.Column("iteration", sa.Integer(), nullable=False),
        sa.Column("test_case_id", sa.String(), nullable=False),
        sa.Column("task_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("turns_count", sa.Integer(), nullable=False),
        sa.Column("dialog", postgresql.JSONB(), nullable=True),
        sa.Column("scores", postgresql.JSONB(), nullable=True),
        sa.Column("judge_feedback", sa.String(), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "agent_id", "skill_id", "run_date", "iteration", "test_case_id",
            name="uq_evaluation_results",
        ),
    )
    op.create_index("ix_evaluation_results_agent_skill", "evaluation_results", ["agent_id", "skill_id"])

    op.create_table(
        "scheduled_tasks",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("schedule_id", sa.String(), nullable=True),
        sa.Column("agent_id", sa.String(), nullable=False),
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
    op.create_index("ix_scheduled_tasks_agent_id", "scheduled_tasks", ["agent_id"])
    op.create_index("ix_scheduled_tasks_status", "scheduled_tasks", ["status"])
    op.create_index("ix_scheduled_tasks_next_run", "scheduled_tasks", ["next_run"])

    op.create_table(
        "stores",
        sa.Column("store_id", sa.String(255), primary_key=True, nullable=False),
        sa.Column("store_data", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_stores_store_id", "stores", ["store_id"])
    op.create_index("ix_stores_updated_at", "stores", ["updated_at"])

    op.create_table(
        "agent_states",
        sa.Column("session_id", sa.String(255), primary_key=True, nullable=False),
        sa.Column("store_id", sa.String(255), nullable=False),
        sa.Column("state_data", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_agent_states_session_id", "agent_states", ["session_id"])
    op.create_index("ix_agent_states_store_id", "agent_states", ["store_id"])
    op.create_index("ix_agent_states_updated_at", "agent_states", ["updated_at"])


def downgrade() -> None:
    op.drop_table("agent_states")
    op.drop_table("stores")
    op.drop_table("scheduled_tasks")
    op.drop_table("evaluation_results")
    op.drop_table("resources")
    op.drop_table("states")
    op.drop_table("tools")
    op.drop_table("nodes")
    op.drop_table("agents_versions")
    op.drop_table("agents")
