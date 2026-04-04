"""Spans перенесены в platform_tracing (отдельная БД).

Revision ID: shared_0004
Revises: shared_0003
Create Date: 2026-04-04
"""

from typing import Sequence, Union

from alembic import op

revision: str = "shared_0004"
down_revision: Union[str, None] = "shared_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("spans")


def downgrade() -> None:
    raise NotImplementedError("Таблица spans живёт только в platform_tracing")
