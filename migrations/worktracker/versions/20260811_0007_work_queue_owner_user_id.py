"""work_queues.owner_user_id materialization for OpenFGA backfill

Revision ID: worktracker_0007
Revises: worktracker_0006
Create Date: 2026-08-11
"""

from typing import Sequence, Union

from alembic import op

revision: str = "worktracker_0007"
down_revision: Union[str, None] = "worktracker_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE work_queues
        ADD COLUMN IF NOT EXISTS owner_user_id VARCHAR(100)
        """
    )
    op.execute(
        """
        UPDATE work_queues
        SET owner_user_id = company_id
        WHERE owner_user_id IS NULL
        """
    )
    op.execute(
        """
        ALTER TABLE work_queues
        ALTER COLUMN owner_user_id SET NOT NULL
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_work_queues_owner_user_id
        ON work_queues (owner_user_id)
        """
    )


def downgrade() -> None:
    raise NotImplementedError("worktracker_0007 owner_user_id is not reversible")
