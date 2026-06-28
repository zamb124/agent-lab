"""Дроп legacy таблицы variables (переменные переехали в platform_secrets)

Все переменные компании (секретные и обычные) теперь хранятся в микросервисе
secrets (БД platform_secrets, версионируемо). Старое key-value хранилище `variables`
в shared БД и его routing `var:` удалены.

Revision ID: shared_0016
Revises: shared_0015
Create Date: 2026-06-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "shared_0016"
down_revision: Union[str, None] = "shared_0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("variables")


def downgrade() -> None:
    op.create_table(
        "variables",
        sa.Column("key", sa.String(), primary_key=True, nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("key", name="uq_variables_key"),
    )
    op.create_index("ix_variables_key_prefix", "variables", ["key"])
    op.create_index("ix_variables_updated_at", "variables", ["updated_at"])
    op.create_index("ix_variables_expired_at", "variables", ["expired_at"])
