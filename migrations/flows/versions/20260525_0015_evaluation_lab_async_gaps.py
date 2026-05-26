"""evaluation lab async execution gaps

Revision ID: 20260525_0015
Revises: 20260525_0014
Create Date: 2026-05-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260525_0015"
down_revision = "20260525_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "evaluation_suite_versions",
        sa.Column("flow_config_version", sa.String(), nullable=False, server_default=""),
    )
    op.alter_column("evaluation_suite_versions", "flow_config_version", server_default=None)
    op.add_column(
        "evaluation_runs",
        sa.Column("flow_config_version", sa.String(), nullable=False, server_default=""),
    )
    op.alter_column("evaluation_runs", "flow_config_version", server_default=None)
    op.add_column("evaluation_runs", sa.Column("taskiq_task_id", sa.String(), nullable=True))

    op.create_table(
        "evaluation_annotations",
        sa.Column("annotation_id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("case_run_id", sa.String(), nullable=True),
        sa.Column("company_id", sa.String(), nullable=False),
        sa.Column("case_id", sa.String(), nullable=True),
        sa.Column("annotation_type", sa.String(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["evaluation_runs.run_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["case_run_id"],
            ["evaluation_case_runs.case_run_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("annotation_id"),
    )
    op.create_index(
        "ix_evaluation_annotations_company_run",
        "evaluation_annotations",
        ["company_id", "run_id"],
    )
    op.create_index(
        "ix_evaluation_annotations_company_case_run",
        "evaluation_annotations",
        ["company_id", "case_run_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_evaluation_annotations_company_case_run",
        table_name="evaluation_annotations",
    )
    op.drop_index("ix_evaluation_annotations_company_run", table_name="evaluation_annotations")
    op.drop_table("evaluation_annotations")
    op.drop_column("evaluation_runs", "taskiq_task_id")
    op.drop_column("evaluation_runs", "flow_config_version")
    op.drop_column("evaluation_suite_versions", "flow_config_version")
