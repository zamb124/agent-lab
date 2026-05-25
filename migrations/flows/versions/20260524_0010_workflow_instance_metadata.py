"""workflow instance metadata columns

Revision ID: 20260524_0010
Revises: 20260524_0009
Create Date: 2026-05-24
"""

from __future__ import annotations

from alembic import op

revision = "20260524_0010"
down_revision = "20260524_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE workflow_instances ADD COLUMN IF NOT EXISTS flow_id VARCHAR")
    op.execute("ALTER TABLE workflow_instances ADD COLUMN IF NOT EXISTS context_id VARCHAR")
    op.execute("ALTER TABLE workflow_instances ADD COLUMN IF NOT EXISTS task_id VARCHAR")
    op.execute("ALTER TABLE workflow_instances ADD COLUMN IF NOT EXISTS user_id VARCHAR")
    op.execute("ALTER TABLE workflow_instances ADD COLUMN IF NOT EXISTS flow_branch_id VARCHAR")
    op.execute("ALTER TABLE workflow_instances ADD COLUMN IF NOT EXISTS last_event_at TIMESTAMPTZ")

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_workflow_instances_company_flow_updated "
        "ON workflow_instances (company_id, flow_id, updated_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_workflow_instances_company_user_updated "
        "ON workflow_instances (company_id, user_id, updated_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_workflow_instances_company_task "
        "ON workflow_instances (company_id, task_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_workflow_instances_company_context "
        "ON workflow_instances (company_id, context_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_workflow_instances_company_updated "
        "ON workflow_instances (company_id, updated_at)"
    )


def downgrade() -> None:
    # No-op intentionally: current 0009 already defines these columns for fresh installs.
    pass
