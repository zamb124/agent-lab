"""evaluation lab enterprise backend gaps

Revision ID: 20260525_0019
Revises: 20260525_0018
Create Date: 2026-05-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260525_0019"
down_revision = "20260525_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evaluation_pairwise_judgments",
        sa.Column("pairwise_judgment_id", sa.String(), nullable=False),
        sa.Column("company_id", sa.String(), nullable=False),
        sa.Column("suite_id", sa.String(), nullable=False),
        sa.Column("flow_id", sa.String(), nullable=False),
        sa.Column("branch_id", sa.String(), nullable=False),
        sa.Column("left_run_id", sa.String(), nullable=False),
        sa.Column("right_run_id", sa.String(), nullable=False),
        sa.Column("left_case_run_id", sa.String(), nullable=False),
        sa.Column("right_case_run_id", sa.String(), nullable=False),
        sa.Column("mode", sa.String(), nullable=False),
        sa.Column("preferred", sa.String(), nullable=False),
        sa.Column("rubric_version_id", sa.String(), nullable=True),
        sa.Column("scores", postgresql.JSONB(), nullable=False),
        sa.Column("feedback", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["suite_id"], ["evaluation_suites.suite_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["left_run_id"], ["evaluation_runs.run_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["right_run_id"], ["evaluation_runs.run_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["left_case_run_id"],
            ["evaluation_case_runs.case_run_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["right_case_run_id"],
            ["evaluation_case_runs.case_run_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["rubric_version_id"],
            ["evaluation_rubric_versions.rubric_version_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("pairwise_judgment_id"),
    )
    op.create_index(
        "ix_evaluation_pairwise_judgments_company_suite",
        "evaluation_pairwise_judgments",
        ["company_id", "suite_id", "created_at"],
    )
    op.create_index(
        "ix_evaluation_pairwise_judgments_company_left_case_run",
        "evaluation_pairwise_judgments",
        ["company_id", "left_case_run_id"],
    )
    op.create_index(
        "ix_evaluation_pairwise_judgments_company_right_case_run",
        "evaluation_pairwise_judgments",
        ["company_id", "right_case_run_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_evaluation_pairwise_judgments_company_right_case_run",
        table_name="evaluation_pairwise_judgments",
    )
    op.drop_index(
        "ix_evaluation_pairwise_judgments_company_left_case_run",
        table_name="evaluation_pairwise_judgments",
    )
    op.drop_index(
        "ix_evaluation_pairwise_judgments_company_suite",
        table_name="evaluation_pairwise_judgments",
    )
    op.drop_table("evaluation_pairwise_judgments")
