"""Нормализация call_type: устаревший audio -> video."""

from alembic import op

revision = "sync_0008"
down_revision = "sync_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE sync_calls SET call_type = 'video' WHERE call_type = 'audio'")
    op.execute("UPDATE sync_call_links SET call_type = 'video' WHERE call_type = 'audio'")


def downgrade() -> None:
    pass
