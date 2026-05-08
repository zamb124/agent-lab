"""Удаление shared-ресурсов типов rag/prompt/secret/http/cache из таблицы resources.

Revision ID: agents_0007
Revises: agents_0006
Create Date: 2026-05-08
"""

from typing import Sequence, Union

from alembic import op

revision: str = "agents_0007"
down_revision: Union[str, None] = "agents_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DEPRECATED_TYPES = ("rag", "prompt", "secret", "http", "cache")


def upgrade() -> None:
    for t in _DEPRECATED_TYPES:
        op.execute(
            f"DELETE FROM resources WHERE key LIKE 'resource:%' AND value->>'type' = '{t}'"
        )


def downgrade() -> None:
    pass
