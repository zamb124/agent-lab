"""evaluation run usage totals

Revision ID: 20260525_0017
Revises: 20260525_0016
Create Date: 2026-05-25
"""

from __future__ import annotations

from alembic import op

revision = "20260525_0017"
down_revision = "20260525_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE evaluation_runs ADD COLUMN IF NOT EXISTS input_tokens INTEGER NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE evaluation_runs ADD COLUMN IF NOT EXISTS output_tokens INTEGER NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE evaluation_runs ADD COLUMN IF NOT EXISTS total_tokens INTEGER NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE evaluation_runs ADD COLUMN IF NOT EXISTS billing_quantity INTEGER NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE evaluation_runs ALTER COLUMN input_tokens DROP DEFAULT")
    op.execute("ALTER TABLE evaluation_runs ALTER COLUMN output_tokens DROP DEFAULT")
    op.execute("ALTER TABLE evaluation_runs ALTER COLUMN total_tokens DROP DEFAULT")
    op.execute("ALTER TABLE evaluation_runs ALTER COLUMN billing_quantity DROP DEFAULT")


def downgrade() -> None:
    op.execute("ALTER TABLE evaluation_runs DROP COLUMN IF EXISTS billing_quantity")
    op.execute("ALTER TABLE evaluation_runs DROP COLUMN IF EXISTS total_tokens")
    op.execute("ALTER TABLE evaluation_runs DROP COLUMN IF EXISTS output_tokens")
    op.execute("ALTER TABLE evaluation_runs DROP COLUMN IF EXISTS input_tokens")
