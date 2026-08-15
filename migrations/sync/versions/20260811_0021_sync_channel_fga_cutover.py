"""sync OpenFGA cutover: drop role from sync_channel_members

Revision ID: sync_0021
Revises: sync_0020
Create Date: 2026-08-11
"""

from typing import Sequence, Union

from alembic import op

revision: str = "sync_0021"
down_revision: Union[str, None] = "sync_0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("sync_channel_members", "role")


def downgrade() -> None:
    raise NotImplementedError(
        "sync_0021 is a hard cutover; ACL lives in OpenFGA only; restore from backup if needed"
    )
