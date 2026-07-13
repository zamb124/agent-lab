"""WorkItem interaction spec (operator_handoff embedded chat policy)

Revision ID: worktracker_0005
Revises: worktracker_0004
Create Date: 2026-07-13
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "worktracker_0005"
down_revision: Union[str, None] = "worktracker_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    if "interaction" not in _table_columns("work_items"):
        op.add_column(
            "work_items",
            sa.Column(
                "interaction",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
        )


def downgrade() -> None:
    if "interaction" in _table_columns("work_items"):
        op.drop_column("work_items", "interaction")
