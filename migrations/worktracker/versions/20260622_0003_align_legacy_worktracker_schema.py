"""Выравнивание legacy-схемы worktracker с текущими моделями

Revision ID: worktracker_0003
Revises: worktracker_0002
Create Date: 2026-06-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "worktracker_0003"
down_revision: Union[str, None] = "worktracker_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    board_columns = _table_columns("work_boards")
    if "board_key" not in board_columns:
        op.add_column(
            "work_boards",
            sa.Column(
                "board_key",
                sa.String(120),
                nullable=False,
                server_default="generic",
            ),
        )

    comment_columns = _table_columns("work_item_comments")
    if "role" not in comment_columns:
        op.add_column(
            "work_item_comments",
            sa.Column(
                "role",
                sa.String(16),
                nullable=False,
                server_default="system",
            ),
        )

    member_columns = _table_columns("work_queue_members")
    if "user_id" in member_columns and "member_kind" not in member_columns:
        op.add_column(
            "work_queue_members",
            sa.Column("member_kind", sa.String(16), nullable=True),
        )
        op.add_column(
            "work_queue_members",
            sa.Column("member_ref", sa.String(100), nullable=True),
        )
        op.execute(
            """
            UPDATE work_queue_members
            SET member_kind = 'user', member_ref = user_id
            WHERE member_kind IS NULL
            """
        )
        op.alter_column("work_queue_members", "member_kind", nullable=False)
        op.alter_column("work_queue_members", "member_ref", nullable=False)
        op.drop_constraint("work_queue_members_pkey", "work_queue_members", type_="primary")
        op.drop_index("ix_work_queue_members_user", table_name="work_queue_members")
        op.drop_column("work_queue_members", "user_id")
        op.create_primary_key(
            "work_queue_members_pkey",
            "work_queue_members",
            ["work_queue_id", "member_kind", "member_ref"],
        )
        op.create_index(
            "ix_work_queue_members_ref",
            "work_queue_members",
            ["member_kind", "member_ref"],
        )


def downgrade() -> None:
    member_columns = _table_columns("work_queue_members")
    if "member_kind" in member_columns and "user_id" not in member_columns:
        op.add_column(
            "work_queue_members",
            sa.Column("user_id", sa.String(100), nullable=True),
        )
        op.execute(
            """
            UPDATE work_queue_members
            SET user_id = member_ref
            WHERE member_kind = 'user'
            """
        )
        op.drop_index("ix_work_queue_members_ref", table_name="work_queue_members")
        op.drop_constraint("work_queue_members_pkey", "work_queue_members", type_="primary")
        op.drop_column("work_queue_members", "member_kind")
        op.drop_column("work_queue_members", "member_ref")
        op.alter_column("work_queue_members", "user_id", nullable=False)
        op.create_primary_key(
            "work_queue_members_pkey",
            "work_queue_members",
            ["work_queue_id", "user_id"],
        )
        op.create_index(
            "ix_work_queue_members_user",
            "work_queue_members",
            ["user_id"],
        )

    board_columns = _table_columns("work_boards")
    if "board_key" in board_columns:
        op.drop_column("work_boards", "board_key")

    comment_columns = _table_columns("work_item_comments")
    if "role" in comment_columns:
        op.drop_column("work_item_comments", "role")
