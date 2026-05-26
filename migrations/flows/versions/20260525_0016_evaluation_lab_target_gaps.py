"""evaluation lab target backend gaps

Revision ID: 20260525_0016
Revises: 20260525_0015
Create Date: 2026-05-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260525_0016"
down_revision = "20260525_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evaluation_rubrics",
        sa.Column("rubric_id", sa.String(), nullable=False),
        sa.Column("company_id", sa.String(), nullable=False),
        sa.Column("flow_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("tags", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("rubric_id"),
        sa.UniqueConstraint(
            "company_id",
            "flow_id",
            "name",
            name="uq_evaluation_rubrics_company_flow_name",
        ),
    )
    op.create_index(
        "ix_evaluation_rubrics_company_flow",
        "evaluation_rubrics",
        ["company_id", "flow_id"],
    )

    op.create_table(
        "evaluation_rubric_versions",
        sa.Column("rubric_version_id", sa.String(), nullable=False),
        sa.Column("rubric_id", sa.String(), nullable=False),
        sa.Column("company_id", sa.String(), nullable=False),
        sa.Column("flow_id", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("pass_threshold", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["rubric_id"], ["evaluation_rubrics.rubric_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("rubric_version_id"),
        sa.UniqueConstraint(
            "company_id",
            "rubric_id",
            "version",
            name="uq_evaluation_rubric_versions_version",
        ),
    )
    op.create_index(
        "ix_evaluation_rubric_versions_company_rubric",
        "evaluation_rubric_versions",
        ["company_id", "rubric_id"],
    )

    op.add_column("evaluation_runs", sa.Column("gate_policy_id", sa.String(), nullable=True))
    op.add_column("evaluation_runs", sa.Column("gate_state", sa.String(), nullable=True))
    op.add_column(
        "evaluation_runs",
        sa.Column("trials", sa.Integer(), nullable=False, server_default="1"),
    )
    op.alter_column("evaluation_runs", "trials", server_default=None)
    op.add_column(
        "evaluation_runs",
        sa.Column("max_concurrency", sa.Integer(), nullable=False, server_default="1"),
    )
    op.alter_column("evaluation_runs", "max_concurrency", server_default=None)
    op.add_column(
        "evaluation_runs",
        sa.Column("total_case_runs", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "evaluation_runs",
        sa.Column("passed_case_runs", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "evaluation_runs",
        sa.Column("failed_case_runs", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "evaluation_runs",
        sa.Column("error_case_runs", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "evaluation_runs",
        sa.Column("canceled_case_runs", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("evaluation_runs", sa.Column("average_duration_ms", sa.Float(), nullable=True))
    op.execute("""
        UPDATE evaluation_runs
        SET total_case_runs = total_cases,
            passed_case_runs = passed_cases,
            failed_case_runs = failed_cases,
            error_case_runs = error_cases,
            canceled_case_runs = canceled_cases
    """)
    op.alter_column("evaluation_runs", "total_case_runs", server_default=None)
    op.alter_column("evaluation_runs", "passed_case_runs", server_default=None)
    op.alter_column("evaluation_runs", "failed_case_runs", server_default=None)
    op.alter_column("evaluation_runs", "error_case_runs", server_default=None)
    op.alter_column("evaluation_runs", "canceled_case_runs", server_default=None)
    op.drop_column("evaluation_runs", "passed_cases")
    op.drop_column("evaluation_runs", "failed_cases")
    op.drop_column("evaluation_runs", "error_cases")
    op.drop_column("evaluation_runs", "canceled_cases")

    op.add_column(
        "evaluation_case_runs",
        sa.Column("trial_index", sa.Integer(), nullable=False, server_default="1"),
    )
    op.alter_column("evaluation_case_runs", "trial_index", server_default=None)
    op.add_column(
        "evaluation_case_runs",
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "evaluation_case_runs",
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "evaluation_case_runs",
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "evaluation_case_runs",
        sa.Column("billing_quantity", sa.Integer(), nullable=False, server_default="0"),
    )
    op.alter_column("evaluation_case_runs", "input_tokens", server_default=None)
    op.alter_column("evaluation_case_runs", "output_tokens", server_default=None)
    op.alter_column("evaluation_case_runs", "total_tokens", server_default=None)
    op.alter_column("evaluation_case_runs", "billing_quantity", server_default=None)
    op.drop_constraint(
        "uq_evaluation_case_runs_run_case",
        "evaluation_case_runs",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_evaluation_case_runs_run_case_trial",
        "evaluation_case_runs",
        ["company_id", "run_id", "case_id", "trial_index"],
    )

    op.create_table(
        "evaluation_baselines",
        sa.Column("baseline_id", sa.String(), nullable=False),
        sa.Column("suite_id", sa.String(), nullable=False),
        sa.Column("company_id", sa.String(), nullable=False),
        sa.Column("flow_id", sa.String(), nullable=False),
        sa.Column("branch_id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["evaluation_runs.run_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["suite_id"], ["evaluation_suites.suite_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("baseline_id"),
        sa.UniqueConstraint(
            "company_id",
            "suite_id",
            "branch_id",
            name="uq_evaluation_baselines_suite_branch",
        ),
    )
    op.create_index(
        "ix_evaluation_baselines_company_suite",
        "evaluation_baselines",
        ["company_id", "suite_id"],
    )

    op.create_table(
        "evaluation_gate_policies",
        sa.Column("gate_policy_id", sa.String(), nullable=False),
        sa.Column("suite_id", sa.String(), nullable=False),
        sa.Column("company_id", sa.String(), nullable=False),
        sa.Column("flow_id", sa.String(), nullable=False),
        sa.Column("branch_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("min_pass_rate", sa.Float(), nullable=False),
        sa.Column("min_average_score", sa.Float(), nullable=True),
        sa.Column("max_failed_case_runs", sa.Integer(), nullable=False),
        sa.Column("max_error_case_runs", sa.Integer(), nullable=False),
        sa.Column("max_average_duration_ms", sa.Integer(), nullable=True),
        sa.Column("require_baseline", sa.Boolean(), nullable=False),
        sa.Column("min_baseline_score_delta", sa.Float(), nullable=True),
        sa.Column("max_baseline_duration_delta_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["suite_id"], ["evaluation_suites.suite_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("gate_policy_id"),
        sa.UniqueConstraint(
            "company_id",
            "suite_id",
            "branch_id",
            "name",
            name="uq_evaluation_gate_policy_name",
        ),
    )
    op.create_index(
        "ix_evaluation_gate_policies_company_suite",
        "evaluation_gate_policies",
        ["company_id", "suite_id"],
    )

    op.create_table(
        "evaluation_gate_results",
        sa.Column("gate_result_id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("gate_policy_id", sa.String(), nullable=False),
        sa.Column("company_id", sa.String(), nullable=False),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("metrics", postgresql.JSONB(), nullable=False),
        sa.Column("violations", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["gate_policy_id"], ["evaluation_gate_policies.gate_policy_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["run_id"], ["evaluation_runs.run_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("gate_result_id"),
        sa.UniqueConstraint("company_id", "run_id", name="uq_evaluation_gate_results_run"),
    )
    op.create_index(
        "ix_evaluation_gate_results_company_policy",
        "evaluation_gate_results",
        ["company_id", "gate_policy_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_evaluation_gate_results_company_policy", table_name="evaluation_gate_results")
    op.drop_table("evaluation_gate_results")
    op.drop_index("ix_evaluation_gate_policies_company_suite", table_name="evaluation_gate_policies")
    op.drop_table("evaluation_gate_policies")
    op.drop_index("ix_evaluation_baselines_company_suite", table_name="evaluation_baselines")
    op.drop_table("evaluation_baselines")
    op.drop_constraint(
        "uq_evaluation_case_runs_run_case_trial",
        "evaluation_case_runs",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_evaluation_case_runs_run_case",
        "evaluation_case_runs",
        ["company_id", "run_id", "case_id"],
    )
    op.drop_column("evaluation_case_runs", "billing_quantity")
    op.drop_column("evaluation_case_runs", "total_tokens")
    op.drop_column("evaluation_case_runs", "output_tokens")
    op.drop_column("evaluation_case_runs", "input_tokens")
    op.drop_column("evaluation_case_runs", "trial_index")
    op.add_column(
        "evaluation_runs",
        sa.Column("canceled_cases", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "evaluation_runs",
        sa.Column("error_cases", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "evaluation_runs",
        sa.Column("failed_cases", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "evaluation_runs",
        sa.Column("passed_cases", sa.Integer(), nullable=False, server_default="0"),
    )
    op.execute("""
        UPDATE evaluation_runs
        SET passed_cases = passed_case_runs,
            failed_cases = failed_case_runs,
            error_cases = error_case_runs,
            canceled_cases = canceled_case_runs
    """)
    op.alter_column("evaluation_runs", "passed_cases", server_default=None)
    op.alter_column("evaluation_runs", "failed_cases", server_default=None)
    op.alter_column("evaluation_runs", "error_cases", server_default=None)
    op.alter_column("evaluation_runs", "canceled_cases", server_default=None)
    op.drop_column("evaluation_runs", "average_duration_ms")
    op.drop_column("evaluation_runs", "canceled_case_runs")
    op.drop_column("evaluation_runs", "error_case_runs")
    op.drop_column("evaluation_runs", "failed_case_runs")
    op.drop_column("evaluation_runs", "passed_case_runs")
    op.drop_column("evaluation_runs", "total_case_runs")
    op.drop_column("evaluation_runs", "max_concurrency")
    op.drop_column("evaluation_runs", "trials")
    op.drop_column("evaluation_runs", "gate_state")
    op.drop_column("evaluation_runs", "gate_policy_id")
    op.drop_index("ix_evaluation_rubric_versions_company_rubric", table_name="evaluation_rubric_versions")
    op.drop_table("evaluation_rubric_versions")
    op.drop_index("ix_evaluation_rubrics_company_flow", table_name="evaluation_rubrics")
    op.drop_table("evaluation_rubrics")
