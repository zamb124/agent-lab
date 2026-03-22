"""sync_files storage_url nullable

Revision ID: sync_0003
Revises: sync_0002
Create Date: 2026-03-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "sync_0003"
down_revision: Union[str, None] = "sync_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Новые записи хранят метаданные в FileRecord (shared DB);
    # storage_url больше не заполняется, старые строки оставляем как есть.
    op.alter_column("sync_files", "storage_url", existing_type=sa.Text(), nullable=True)


def downgrade() -> None:
    # Перед откатом обнуляем строки без URL, иначе NOT NULL упадёт.
    op.execute("UPDATE sync_files SET storage_url = '' WHERE storage_url IS NULL")
    op.alter_column("sync_files", "storage_url", existing_type=sa.Text(), nullable=False)
