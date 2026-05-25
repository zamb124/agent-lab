"""branch-scoped activity idempotency

Revision ID: 20260524_0011
Revises: 20260524_0010
Create Date: 2026-05-24
"""

from __future__ import annotations

from alembic import op

revision = "20260524_0011"
down_revision = "20260524_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE activity_tasks DROP CONSTRAINT IF EXISTS uq_activity_tasks_idempotency_key")
    op.execute(
        "ALTER TABLE activity_tasks DROP CONSTRAINT IF EXISTS "
        + "uq_activity_tasks_branch_idempotency_key"
    )
    op.create_unique_constraint(
        "uq_activity_tasks_branch_idempotency_key",
        "activity_tasks",
        ["company_id", "session_id", "execution_branch_id", "idempotency_key"],
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE activity_tasks DROP CONSTRAINT IF EXISTS "
        + "uq_activity_tasks_branch_idempotency_key"
    )
