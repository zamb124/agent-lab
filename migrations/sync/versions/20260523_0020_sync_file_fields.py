"""Переименовать sync_files mime_type/size_bytes в content_type/file_size.

Revision ID: sync_0020
Revises: sync_0019
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "sync_0020"
down_revision: Union[str, None] = "sync_0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "sync_files",
        "mime_type",
        new_column_name="content_type",
        existing_type=sa.String(length=255),
    )
    op.alter_column(
        "sync_files",
        "size_bytes",
        new_column_name="file_size",
        existing_type=sa.BigInteger(),
    )


def downgrade() -> None:
    op.alter_column(
        "sync_files",
        "file_size",
        new_column_name="size_bytes",
        existing_type=sa.BigInteger(),
    )
    op.alter_column(
        "sync_files",
        "content_type",
        new_column_name="mime_type",
        existing_type=sa.String(length=255),
    )
