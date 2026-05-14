"""sync_call_links.call_type — тип звонка в ссылке

Revision ID: sync_0007
Revises: sync_0006
"""

from typing import Sequence, Union

from alembic import op

revision: str = "sync_0007"
down_revision: Union[str, None] = "sync_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ADD COLUMN IF NOT EXISTS — идемпотентно: dev-БД могла получить колонку
    # вручную через downgrade+upgrade на отредактированной миграции sync_0006.
    op.execute(
        "ALTER TABLE sync_call_links ADD COLUMN IF NOT EXISTS call_type VARCHAR(8) NOT NULL DEFAULT 'video'"
    )


def downgrade() -> None:
    op.drop_column("sync_call_links", "call_type")
