"""rebuild durable activity attempts ledger

Revision ID: 20260525_0012
Revises: 20260524_0011
Create Date: 2026-05-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260525_0012"
down_revision = "20260524_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS activity_attempts CASCADE")
    op.execute("DROP TABLE IF EXISTS activity_tasks CASCADE")

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
    op.create_index("ix_activity_tasks_branch", "activity_tasks", ["execution_branch_id"])
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
    op.create_index("ix_activity_attempts_activity", "activity_attempts", ["activity_id"])
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


def downgrade() -> None:
    op.drop_index("ix_activity_attempts_company_session", table_name="activity_attempts")
    op.drop_index("ix_activity_attempts_branch_status", table_name="activity_attempts")
    op.drop_index("ix_activity_attempts_activity", table_name="activity_attempts")
    op.drop_table("activity_attempts")
    op.drop_index("ix_activity_tasks_node", table_name="activity_tasks")
    op.drop_index("ix_activity_tasks_branch", table_name="activity_tasks")
    op.drop_index("ix_activity_tasks_company_session", table_name="activity_tasks")
    op.drop_table("activity_tasks")
