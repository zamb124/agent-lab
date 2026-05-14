"""Добавляет started_by_user_id в записи звонков."""

import sqlalchemy as sa
from alembic import op

revision = "sync_0010"
down_revision = "sync_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sync_call_recordings",
        sa.Column("started_by_user_id", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sync_call_recordings", "started_by_user_id")
