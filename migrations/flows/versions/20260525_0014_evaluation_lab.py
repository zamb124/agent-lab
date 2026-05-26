"""first-class evaluation lab schema

Revision ID: 20260525_0014
Revises: 20260525_0013
Create Date: 2026-05-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260525_0014"
down_revision = "20260525_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evaluation_suites",
        sa.Column("suite_id", sa.String(), nullable=False),
        sa.Column("company_id", sa.String(), nullable=False),
        sa.Column("flow_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("tags", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("suite_id"),
        sa.UniqueConstraint(
            "company_id",
            "flow_id",
            "name",
            name="uq_evaluation_suites_company_flow_name",
        ),
    )
    op.create_index(
        "ix_evaluation_suites_company_flow",
        "evaluation_suites",
        ["company_id", "flow_id"],
    )

    op.create_table(
        "evaluation_cases",
        sa.Column("case_id", sa.String(), nullable=False),
        sa.Column("suite_id", sa.String(), nullable=False),
        sa.Column("company_id", sa.String(), nullable=False),
        sa.Column("flow_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["suite_id"], ["evaluation_suites.suite_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("case_id"),
        sa.UniqueConstraint("company_id", "suite_id", "name", name="uq_evaluation_cases_suite_name"),
    )
    op.create_index(
        "ix_evaluation_cases_company_suite",
        "evaluation_cases",
        ["company_id", "suite_id"],
    )
    op.create_index(
        "ix_evaluation_cases_company_flow",
        "evaluation_cases",
        ["company_id", "flow_id"],
    )

    op.create_table(
        "evaluation_suite_versions",
        sa.Column("suite_version_id", sa.String(), nullable=False),
        sa.Column("suite_id", sa.String(), nullable=False),
        sa.Column("company_id", sa.String(), nullable=False),
        sa.Column("flow_id", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("suite_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("cases_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["suite_id"], ["evaluation_suites.suite_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("suite_version_id"),
        sa.UniqueConstraint(
            "company_id",
            "suite_id",
            "version",
            name="uq_evaluation_suite_versions_version",
        ),
    )
    op.create_index(
        "ix_evaluation_suite_versions_company_suite",
        "evaluation_suite_versions",
        ["company_id", "suite_id"],
    )

    op.create_table(
        "evaluation_runs",
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("suite_id", sa.String(), nullable=False),
        sa.Column("suite_version_id", sa.String(), nullable=False),
        sa.Column("company_id", sa.String(), nullable=False),
        sa.Column("flow_id", sa.String(), nullable=False),
        sa.Column("branch_id", sa.String(), nullable=False),
        sa.Column("trigger", sa.String(), nullable=False),
        sa.Column("scope", postgresql.JSONB(), nullable=False),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("total_cases", sa.Integer(), nullable=False),
        sa.Column("passed_cases", sa.Integer(), nullable=False),
        sa.Column("failed_cases", sa.Integer(), nullable=False),
        sa.Column("error_cases", sa.Integer(), nullable=False),
        sa.Column("canceled_cases", sa.Integer(), nullable=False),
        sa.Column("average_score", sa.Float(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["suite_version_id"],
            ["evaluation_suite_versions.suite_version_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_index(
        "ix_evaluation_runs_company_suite",
        "evaluation_runs",
        ["company_id", "suite_id"],
    )
    op.create_index(
        "ix_evaluation_runs_company_flow_branch",
        "evaluation_runs",
        ["company_id", "flow_id", "branch_id"],
    )

    op.create_table(
        "evaluation_case_runs",
        sa.Column("case_run_id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("case_id", sa.String(), nullable=False),
        sa.Column("suite_id", sa.String(), nullable=False),
        sa.Column("company_id", sa.String(), nullable=False),
        sa.Column("flow_id", sa.String(), nullable=False),
        sa.Column("branch_id", sa.String(), nullable=False),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("task_id", sa.String(), nullable=True),
        sa.Column("context_id", sa.String(), nullable=True),
        sa.Column("session_id", sa.String(), nullable=True),
        sa.Column("trace_id", sa.String(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("turns_count", sa.Integer(), nullable=False),
        sa.Column("scores", postgresql.JSONB(), nullable=True),
        sa.Column("total_score", sa.Float(), nullable=True),
        sa.Column("judge_feedback", sa.Text(), nullable=True),
        sa.Column("dialog", postgresql.JSONB(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["evaluation_runs.run_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("case_run_id"),
        sa.UniqueConstraint(
            "company_id",
            "run_id",
            "case_id",
            name="uq_evaluation_case_runs_run_case",
        ),
    )
    op.create_index(
        "ix_evaluation_case_runs_company_run",
        "evaluation_case_runs",
        ["company_id", "run_id"],
    )
    op.create_index(
        "ix_evaluation_case_runs_company_case",
        "evaluation_case_runs",
        ["company_id", "case_id"],
    )

    op.create_table(
        "evaluation_run_events",
        sa.Column("event_id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("case_run_id", sa.String(), nullable=True),
        sa.Column("company_id", sa.String(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["evaluation_runs.run_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("event_id"),
        sa.UniqueConstraint(
            "company_id",
            "run_id",
            "sequence",
            name="uq_evaluation_run_events_sequence",
        ),
    )
    op.create_index(
        "ix_evaluation_run_events_company_run",
        "evaluation_run_events",
        ["company_id", "run_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_evaluation_run_events_company_run", table_name="evaluation_run_events")
    op.drop_table("evaluation_run_events")
    op.drop_index("ix_evaluation_case_runs_company_case", table_name="evaluation_case_runs")
    op.drop_index("ix_evaluation_case_runs_company_run", table_name="evaluation_case_runs")
    op.drop_table("evaluation_case_runs")
    op.drop_index("ix_evaluation_runs_company_flow_branch", table_name="evaluation_runs")
    op.drop_index("ix_evaluation_runs_company_suite", table_name="evaluation_runs")
    op.drop_table("evaluation_runs")
    op.drop_index(
        "ix_evaluation_suite_versions_company_suite",
        table_name="evaluation_suite_versions",
    )
    op.drop_table("evaluation_suite_versions")
    op.drop_index("ix_evaluation_cases_company_flow", table_name="evaluation_cases")
    op.drop_index("ix_evaluation_cases_company_suite", table_name="evaluation_cases")
    op.drop_table("evaluation_cases")
    op.drop_index("ix_evaluation_suites_company_flow", table_name="evaluation_suites")
    op.drop_table("evaluation_suites")
