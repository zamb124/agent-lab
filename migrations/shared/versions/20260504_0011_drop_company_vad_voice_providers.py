"""Удаление per-company записей VAD: VAD только deployment-default.

Revision ID: shared_0011
Revises: shared_0010
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "shared_0011"
down_revision: Union[str, None] = "shared_0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("DELETE FROM company_voice_providers WHERE kind = 'vad'")
    )


def downgrade() -> None:
    pass
