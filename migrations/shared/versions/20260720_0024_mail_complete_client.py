"""Mail complete client: flags, backfill cursor, binding members.

Revision ID: shared_0024
Revises: shared_0023
Create Date: 2026-07-20
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "shared_0024"
down_revision: Union[str, None] = "shared_0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "mail_messages",
        sa.Column("flagged", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "mail_messages",
        sa.Column("answered", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "mail_messages",
        sa.Column("draft", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.alter_column("mail_messages", "user_id", existing_type=sa.String(length=255), nullable=True)

    op.add_column(
        "mailbox_sync_cursors",
        sa.Column(
            "backfill_completed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "mailbox_sync_cursors",
        sa.Column("oldest_uid", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "mailbox_sync_cursors",
        sa.Column("last_reconcile_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "mailbox_binding_members",
        sa.Column("mailbox_binding_id", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("company_id", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "mailbox_binding_id",
            "user_id",
            name="pk_mailbox_binding_members",
        ),
        sa.CheckConstraint(
            "role IN ('member','manager')",
            name="mailbox_binding_members_role_check",
        ),
    )
    op.create_index(
        "ix_mailbox_binding_members_company_id",
        "mailbox_binding_members",
        ["company_id"],
    )
    op.create_index(
        "ix_mailbox_binding_members_user_id",
        "mailbox_binding_members",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_mailbox_binding_members_user_id", table_name="mailbox_binding_members")
    op.drop_index("ix_mailbox_binding_members_company_id", table_name="mailbox_binding_members")
    op.drop_table("mailbox_binding_members")
    op.drop_column("mailbox_sync_cursors", "last_reconcile_at")
    op.drop_column("mailbox_sync_cursors", "oldest_uid")
    op.drop_column("mailbox_sync_cursors", "backfill_completed")
    op.alter_column("mail_messages", "user_id", existing_type=sa.String(length=255), nullable=False)
    op.drop_column("mail_messages", "draft")
    op.drop_column("mail_messages", "answered")
    op.drop_column("mail_messages", "flagged")
