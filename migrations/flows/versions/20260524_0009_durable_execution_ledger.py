"""durable execution ledger

Revision ID: 20260524_0009
Revises: 20260523_0008
Create Date: 2026-05-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260524_0009"
down_revision = "agents_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workflow_instances",
        sa.Column("workflow_instance_id", sa.String(), nullable=False),
        sa.Column("company_id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("flow_id", sa.String(), nullable=True),
        sa.Column("context_id", sa.String(), nullable=True),
        sa.Column("task_id", sa.String(), nullable=True),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("flow_branch_id", sa.String(), nullable=True),
        sa.Column("active_execution_branch_id", sa.String(), nullable=False),
        sa.Column("head_sequence", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("head_state_hash", sa.String(), nullable=True),
        sa.Column("latest_snapshot_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="running"),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("workflow_instance_id"),
        sa.UniqueConstraint("company_id", "session_id", name="uq_workflow_instances_company_session"),
    )
    op.create_index(
        "ix_workflow_instances_company_status",
        "workflow_instances",
        ["company_id", "status"],
    )
    op.create_index(
        "ix_workflow_instances_company_flow_updated",
        "workflow_instances",
        ["company_id", "flow_id", "updated_at"],
    )
    op.create_index(
        "ix_workflow_instances_company_user_updated",
        "workflow_instances",
        ["company_id", "user_id", "updated_at"],
    )
    op.create_index(
        "ix_workflow_instances_company_task",
        "workflow_instances",
        ["company_id", "task_id"],
    )
    op.create_index(
        "ix_workflow_instances_company_context",
        "workflow_instances",
        ["company_id", "context_id"],
    )
    op.create_index(
        "ix_workflow_instances_company_updated",
        "workflow_instances",
        ["company_id", "updated_at"],
    )

    op.create_table(
        "execution_branches",
        sa.Column("execution_branch_id", sa.String(), nullable=False),
        sa.Column("company_id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("parent_execution_branch_id", sa.String(), nullable=True),
        sa.Column("base_sequence", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("base_state_hash", sa.String(), nullable=True),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("execution_branch_id"),
    )
    op.create_index(
        "ix_execution_branches_company_session",
        "execution_branches",
        ["company_id", "session_id"],
    )
    op.create_index(
        "ix_execution_branches_parent",
        "execution_branches",
        ["parent_execution_branch_id"],
    )

    op.create_table(
        "workflow_events",
        sa.Column("event_id", sa.String(), nullable=False),
        sa.Column("company_id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("execution_branch_id", sa.String(), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("state_delta", postgresql.JSONB(), nullable=False),
        sa.Column("prev_state_hash", sa.String(), nullable=True),
        sa.Column("next_state_hash", sa.String(), nullable=False),
        sa.Column("causation_id", sa.String(), nullable=True),
        sa.Column("correlation_id", sa.String(), nullable=True),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("event_id"),
        sa.UniqueConstraint(
            "company_id",
            "session_id",
            "execution_branch_id",
            "sequence",
            name="uq_workflow_events_sequence",
        ),
    )
    op.create_index(
        "ix_workflow_events_company_session_sequence",
        "workflow_events",
        ["company_id", "session_id", "sequence"],
    )
    op.create_index(
        "ix_workflow_events_branch_sequence",
        "workflow_events",
        ["execution_branch_id", "sequence"],
    )
    op.create_index("ix_workflow_events_type", "workflow_events", ["event_type"])

    op.create_table(
        "workflow_snapshots",
        sa.Column("snapshot_id", sa.String(), nullable=False),
        sa.Column("company_id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("execution_branch_id", sa.String(), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("state_json", postgresql.JSONB(), nullable=False),
        sa.Column("state_hash", sa.String(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("snapshot_id"),
        sa.UniqueConstraint(
            "company_id",
            "session_id",
            "execution_branch_id",
            "sequence",
            name="uq_workflow_snapshots_sequence",
        ),
    )
    op.create_index(
        "ix_workflow_snapshots_company_session_sequence",
        "workflow_snapshots",
        ["company_id", "session_id", "sequence"],
    )
    op.create_index(
        "ix_workflow_snapshots_branch_sequence",
        "workflow_snapshots",
        ["execution_branch_id", "sequence"],
    )

    op.create_table(
        "activity_tasks",
        sa.Column("activity_id", sa.String(), nullable=False),
        sa.Column("company_id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("execution_branch_id", sa.String(), nullable=False),
        sa.Column("node_id", sa.String(), nullable=True),
        sa.Column("tool_call_id", sa.String(), nullable=True),
        sa.Column("activity_type", sa.String(), nullable=False),
        sa.Column("input_hash", sa.String(), nullable=False),
        sa.Column("idempotency_key", sa.String(), nullable=True),
        sa.Column("side_effect_policy", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("activity_id"),
        sa.UniqueConstraint(
            "company_id",
            "session_id",
            "execution_branch_id",
            "idempotency_key",
            name="uq_activity_tasks_branch_idempotency_key",
        ),
    )
    op.create_index(
        "ix_activity_tasks_company_session",
        "activity_tasks",
        ["company_id", "session_id"],
    )
    op.create_index(
        "ix_activity_tasks_branch",
        "activity_tasks",
        ["execution_branch_id"],
    )
    op.create_index("ix_activity_tasks_node", "activity_tasks", ["node_id"])

    op.create_table(
        "activity_attempts",
        sa.Column("activity_attempt_id", sa.String(), nullable=False),
        sa.Column("activity_id", sa.String(), nullable=False),
        sa.Column("company_id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("execution_branch_id", sa.String(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("result_json", postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["activity_id"], ["activity_tasks.activity_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("activity_attempt_id"),
        sa.UniqueConstraint(
            "activity_id",
            "attempt",
            name="uq_activity_attempts_activity_attempt",
        ),
    )
    op.create_index(
        "ix_activity_attempts_activity",
        "activity_attempts",
        ["activity_id"],
    )
    op.create_index(
        "ix_activity_attempts_branch_status",
        "activity_attempts",
        ["execution_branch_id", "status"],
    )
    op.create_index(
        "ix_activity_attempts_company_session",
        "activity_attempts",
        ["company_id", "session_id"],
    )

    op.execute("DROP TABLE IF EXISTS flow_states CASCADE")
    op.execute("DROP TABLE IF EXISTS stores CASCADE")
    op.execute("DROP TABLE IF EXISTS states CASCADE")


def downgrade() -> None:
    op.drop_index("ix_activity_attempts_company_session", table_name="activity_attempts")
    op.drop_index("ix_activity_attempts_branch_status", table_name="activity_attempts")
    op.drop_index("ix_activity_attempts_activity", table_name="activity_attempts")
    op.drop_table("activity_attempts")
    op.drop_index("ix_activity_tasks_node", table_name="activity_tasks")
    op.drop_index("ix_activity_tasks_branch", table_name="activity_tasks")
    op.drop_index("ix_activity_tasks_company_session", table_name="activity_tasks")
    op.drop_table("activity_tasks")

    op.drop_index("ix_workflow_snapshots_branch_sequence", table_name="workflow_snapshots")
    op.drop_index("ix_workflow_snapshots_company_session_sequence", table_name="workflow_snapshots")
    op.drop_table("workflow_snapshots")

    op.drop_index("ix_workflow_events_type", table_name="workflow_events")
    op.drop_index("ix_workflow_events_branch_sequence", table_name="workflow_events")
    op.drop_index("ix_workflow_events_company_session_sequence", table_name="workflow_events")
    op.drop_table("workflow_events")

    op.drop_index("ix_execution_branches_parent", table_name="execution_branches")
    op.drop_index("ix_execution_branches_company_session", table_name="execution_branches")
    op.drop_table("execution_branches")

    op.drop_index("ix_workflow_instances_company_context", table_name="workflow_instances")
    op.drop_index("ix_workflow_instances_company_task", table_name="workflow_instances")
    op.drop_index("ix_workflow_instances_company_user_updated", table_name="workflow_instances")
    op.drop_index("ix_workflow_instances_company_flow_updated", table_name="workflow_instances")
    op.drop_index("ix_workflow_instances_company_updated", table_name="workflow_instances")
    op.drop_index("ix_workflow_instances_company_status", table_name="workflow_instances")
    op.drop_table("workflow_instances")
