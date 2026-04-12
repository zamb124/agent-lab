"""namespaces JSON: default provider pgvector for existing rows

Revision ID: shared_0008
Revises: shared_0007
Create Date: 2026-04-10
"""

from typing import Sequence, Union

from alembic import op

revision: str = "shared_0008"
down_revision: Union[str, None] = "shared_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE namespaces
        SET value = jsonb_set(
            value,
            '{provider}',
            to_jsonb('pgvector'::text),
            true
        )
        WHERE (value->>'provider') IS NULL
           OR (value->>'provider') = '';
        """
    )


def downgrade() -> None:
    pass
