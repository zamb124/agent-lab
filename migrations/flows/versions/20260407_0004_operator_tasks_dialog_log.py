"""operator_tasks: добавить dialog_log (JSONB) для хранения реплик takeover

Revision ID: agents_0004
Revises: agents_0003
Create Date: 2026-04-07
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "agents_0004"
down_revision: Union[str, None] = "agents_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "operator_tasks",
        sa.Column("dialog_log", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("operator_tasks", "dialog_log")
