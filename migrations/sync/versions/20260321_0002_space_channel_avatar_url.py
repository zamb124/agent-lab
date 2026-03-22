"""avatar_url for spaces and channels

Revision ID: sync_0002
Revises: sync_0001
Create Date: 2026-03-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "sync_0002"
down_revision: Union[str, None] = "sync_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sync_spaces", sa.Column("avatar_url", sa.Text(), nullable=True))
    op.add_column("sync_channels", sa.Column("avatar_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("sync_channels", "avatar_url")
    op.drop_column("sync_spaces", "avatar_url")
