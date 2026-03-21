"""sync_channel_members: last_read_at

Revision ID: c7d8e9f0a1b2
Revises: ab5b3040c868
Create Date: 2026-03-20

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'c7d8e9f0a1b2'
down_revision: Union[str, None] = 'ab5b3040c868'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # IF NOT EXISTS: колонка могла уже появиться из SyncDatabase._ensure_schema_columns при старте сервиса.
    op.execute(
        "ALTER TABLE sync_channel_members "
        "ADD COLUMN IF NOT EXISTS last_read_at TIMESTAMP WITH TIME ZONE"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE sync_channel_members DROP COLUMN IF EXISTS last_read_at"
    )
