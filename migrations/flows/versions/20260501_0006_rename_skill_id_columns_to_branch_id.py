"""Legacy: branch_id в operator_tasks при отсутствии

Revision ID: agents_0006
Revises: agents_0005
Create Date: 2026-05-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "agents_0006"
down_revision: Union[str, None] = "agents_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(conn, table: str, column: str) -> bool:
    row = conn.execute(
        sa.text(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = :t
              AND column_name = :c
            """
        ),
        {"t": table, "c": column},
    )
    return row.first() is not None


def upgrade() -> None:
    conn = op.get_bind()

    if _has_column(conn, "operator_tasks", "skill_id") and not _has_column(
        conn, "operator_tasks", "branch_id"
    ):
        op.alter_column("operator_tasks", "skill_id", new_column_name="branch_id")
    elif not _has_column(conn, "operator_tasks", "branch_id"):
        op.add_column(
            "operator_tasks",
            sa.Column(
                "branch_id",
                sa.String(length=255),
                nullable=False,
                server_default="default",
            ),
        )
        op.alter_column("operator_tasks", "branch_id", server_default=None)


def downgrade() -> None:
    conn = op.get_bind()

    if _has_column(conn, "operator_tasks", "branch_id") and not _has_column(
        conn, "operator_tasks", "skill_id"
    ):
        op.alter_column("operator_tasks", "branch_id", new_column_name="skill_id")
