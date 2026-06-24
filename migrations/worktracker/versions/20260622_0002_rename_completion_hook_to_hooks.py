"""Переименование completion_hook → hooks (массив WorkItemHook)

Revision ID: worktracker_0002
Revises: worktracker_0001
Create Date: 2026-06-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "worktracker_0002"
down_revision: Union[str, None] = "worktracker_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("work_items")}
    if "hooks" in columns:
        return
    if "completion_hook" not in columns:
        op.add_column(
            "work_items",
            sa.Column(
                "hooks",
                postgresql.JSONB(),
                nullable=False,
                server_default="[]",
            ),
        )
        return

    op.add_column(
        "work_items",
        sa.Column(
            "hooks",
            postgresql.JSONB(),
            nullable=True,
        ),
    )
    op.execute(
        """
        UPDATE work_items
        SET hooks = CASE
            WHEN completion_hook IS NULL THEN '[]'::jsonb
            WHEN jsonb_typeof(completion_hook) = 'array' THEN completion_hook
            ELSE jsonb_build_array(
                completion_hook || jsonb_build_object('event', 'completed')
            )
        END
        """
    )
    op.alter_column("work_items", "hooks", nullable=False, server_default="[]")
    op.drop_column("work_items", "completion_hook")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("work_items")}
    if "completion_hook" in columns:
        return
    if "hooks" not in columns:
        return

    op.add_column(
        "work_items",
        sa.Column("completion_hook", postgresql.JSONB(), nullable=True),
    )
    op.execute(
        """
        UPDATE work_items
        SET completion_hook = CASE
            WHEN hooks IS NULL OR jsonb_array_length(hooks) = 0 THEN NULL
            ELSE hooks->0
        END
        """
    )
    op.drop_column("work_items", "hooks")
