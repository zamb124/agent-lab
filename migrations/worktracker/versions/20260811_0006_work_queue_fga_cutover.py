"""worktracker OpenFGA cutover: drop work_queue_members

Revision ID: worktracker_0006
Revises: worktracker_0005
Create Date: 2026-08-11
"""

from typing import Sequence, Union

from alembic import op

revision: str = "worktracker_0006"
down_revision: Union[str, None] = "worktracker_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("work_queue_members")


def downgrade() -> None:
    raise NotImplementedError(
        "worktracker_0006 is a hard cutover; ACL lives in OpenFGA only; restore from backup if needed"
    )
