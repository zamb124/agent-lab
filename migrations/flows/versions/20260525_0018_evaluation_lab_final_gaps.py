"""evaluation lab final backend gaps

Revision ID: 20260525_0018
Revises: 20260525_0017
Create Date: 2026-05-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260525_0018"
down_revision = "20260525_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("evaluation_suites", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("evaluation_rubrics", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("evaluation_gate_policies", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("evaluation_runs", sa.Column("idempotency_key", sa.String(), nullable=True))
    op.create_unique_constraint(
        "uq_evaluation_runs_idempotency",
        "evaluation_runs",
        ["company_id", "suite_id", "branch_id", "idempotency_key"],
    )

    op.create_table(
        "evaluation_run_jobs",
        sa.Column("run_job_id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("company_id", sa.String(), nullable=False),
        sa.Column("taskiq_task_id", sa.String(), nullable=False),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("context_data", postgresql.JSONB(), nullable=False),
        sa.Column("trace_context", postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("enqueued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["evaluation_runs.run_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("run_job_id"),
        sa.UniqueConstraint("company_id", "run_id", name="uq_evaluation_run_jobs_run"),
        sa.UniqueConstraint("company_id", "taskiq_task_id", name="uq_evaluation_run_jobs_taskiq"),
    )
    op.create_index(
        "ix_evaluation_run_jobs_company_state",
        "evaluation_run_jobs",
        ["company_id", "state", "created_at"],
    )

    op.create_table(
        "evaluation_monitors",
        sa.Column("monitor_id", sa.String(), nullable=False),
        sa.Column("suite_id", sa.String(), nullable=False),
        sa.Column("company_id", sa.String(), nullable=False),
        sa.Column("flow_id", sa.String(), nullable=False),
        sa.Column("branch_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("sampling_rate", sa.Float(), nullable=False),
        sa.Column("max_traces_per_sample", sa.Integer(), nullable=False),
        sa.Column("filter", postgresql.JSONB(), nullable=False),
        sa.Column("gate_policy_id", sa.String(), nullable=True),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["suite_id"], ["evaluation_suites.suite_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["gate_policy_id"],
            ["evaluation_gate_policies.gate_policy_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("monitor_id"),
        sa.UniqueConstraint(
            "company_id",
            "suite_id",
            "branch_id",
            "name",
            name="uq_evaluation_monitors_name",
        ),
    )
    op.create_index(
        "ix_evaluation_monitors_company_suite",
        "evaluation_monitors",
        ["company_id", "suite_id"],
    )
    op.create_index(
        "ix_evaluation_monitors_company_flow_branch",
        "evaluation_monitors",
        ["company_id", "flow_id", "branch_id"],
    )

    op.create_table(
        "evaluation_monitor_observations",
        sa.Column("observation_id", sa.String(), nullable=False),
        sa.Column("monitor_id", sa.String(), nullable=False),
        sa.Column("suite_id", sa.String(), nullable=False),
        sa.Column("company_id", sa.String(), nullable=False),
        sa.Column("flow_id", sa.String(), nullable=False),
        sa.Column("branch_id", sa.String(), nullable=False),
        sa.Column("trace_id", sa.String(), nullable=False),
        sa.Column("task_id", sa.String(), nullable=True),
        sa.Column("session_id", sa.String(), nullable=True),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("span_count", sa.Integer(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("sampled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("curated_case_id", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["monitor_id"], ["evaluation_monitors.monitor_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["suite_id"], ["evaluation_suites.suite_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("observation_id"),
        sa.UniqueConstraint(
            "company_id",
            "monitor_id",
            "trace_id",
            name="uq_evaluation_monitor_observations_trace",
        ),
    )
    op.create_index(
        "ix_evaluation_monitor_observations_company_monitor",
        "evaluation_monitor_observations",
        ["company_id", "monitor_id", "sampled_at"],
    )
    op.create_index(
        "ix_evaluation_monitor_observations_company_trace",
        "evaluation_monitor_observations",
        ["company_id", "trace_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_evaluation_monitor_observations_company_trace",
        table_name="evaluation_monitor_observations",
    )
    op.drop_index(
        "ix_evaluation_monitor_observations_company_monitor",
        table_name="evaluation_monitor_observations",
    )
    op.drop_table("evaluation_monitor_observations")
    op.drop_index("ix_evaluation_monitors_company_flow_branch", table_name="evaluation_monitors")
    op.drop_index("ix_evaluation_monitors_company_suite", table_name="evaluation_monitors")
    op.drop_table("evaluation_monitors")
    op.drop_index("ix_evaluation_run_jobs_company_state", table_name="evaluation_run_jobs")
    op.drop_table("evaluation_run_jobs")
    op.drop_constraint("uq_evaluation_runs_idempotency", "evaluation_runs", type_="unique")
    op.drop_column("evaluation_runs", "idempotency_key")
    op.drop_column("evaluation_gate_policies", "archived_at")
    op.drop_column("evaluation_rubrics", "archived_at")
    op.drop_column("evaluation_suites", "archived_at")
