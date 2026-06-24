"""Базовая миграция БД platform_worktracker (ядро задач WorkItem)

Revision ID: worktracker_0001
Revises:
Create Date: 2026-06-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "worktracker_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "work_items",
        sa.Column("work_item_id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("company_id", sa.String(100), nullable=False),
        sa.Column("namespace", sa.String(100), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("kind", sa.String(32), nullable=False, server_default="generic"),
        sa.Column("state", sa.String(32), nullable=False, server_default="open"),
        sa.Column("board_id", sa.String(64), nullable=True),
        sa.Column("board_column_id", sa.String(64), nullable=True),
        sa.Column("priority", sa.String(16), nullable=False, server_default="normal"),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("labels", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("created_by", postgresql.JSONB(), nullable=False),
        sa.Column("assignment", postgresql.JSONB(), nullable=False),
        sa.Column("blocking", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("hooks", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("resolution", postgresql.JSONB(), nullable=True),
        sa.Column("links", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_work_items_company", "work_items", ["company_id"])
    op.create_index("ix_work_items_company_state", "work_items", ["company_id", "state"])
    op.create_index("ix_work_items_company_board", "work_items", ["company_id", "board_id"])
    op.create_index(
        "ix_work_items_company_namespace", "work_items", ["company_id", "namespace"]
    )

    op.create_table(
        "work_queues",
        sa.Column("work_queue_id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("company_id", sa.String(100), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("company_id", "slug", name="uq_work_queues_company_slug"),
    )
    op.create_index("ix_work_queues_company", "work_queues", ["company_id"])

    op.create_table(
        "work_queue_members",
        sa.Column("work_queue_id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("member_kind", sa.String(16), primary_key=True, nullable=False),
        sa.Column("member_ref", sa.String(100), primary_key=True, nullable=False),
        sa.Column("company_id", sa.String(100), nullable=False),
        sa.Column("role", sa.String(32), nullable=False, server_default="member"),
    )
    op.create_index("ix_work_queue_members_company", "work_queue_members", ["company_id"])
    op.create_index(
        "ix_work_queue_members_ref", "work_queue_members", ["member_kind", "member_ref"]
    )

    op.create_table(
        "work_boards",
        sa.Column("board_id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("company_id", sa.String(100), nullable=False),
        sa.Column("namespace", sa.String(100), nullable=True),
        sa.Column("board_key", sa.String(120), nullable=False, server_default="generic"),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("columns", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_work_boards_company", "work_boards", ["company_id"])
    op.create_index(
        "ix_work_boards_company_namespace", "work_boards", ["company_id", "namespace"]
    )

    op.create_table(
        "work_item_comments",
        sa.Column("comment_id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("work_item_id", sa.String(64), nullable=False),
        sa.Column("company_id", sa.String(100), nullable=False),
        sa.Column("author", postgresql.JSONB(), nullable=False),
        sa.Column("role", sa.String(16), nullable=False, server_default="system"),
        sa.Column("text", sa.Text(), nullable=False, server_default=""),
        sa.Column("file_ids", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_work_item_comments_work_item", "work_item_comments", ["work_item_id"]
    )
    op.create_index("ix_work_item_comments_company", "work_item_comments", ["company_id"])


def downgrade() -> None:
    op.drop_table("work_item_comments")
    op.drop_table("work_boards")
    op.drop_table("work_queue_members")
    op.drop_table("work_queues")
    op.drop_table("work_items")
