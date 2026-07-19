"""Mailbox IMAP sync cursors for background mail sync.

Revision ID: shared_0020
Revises: shared_0019
Create Date: 2026-07-19
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "shared_0020"
down_revision: Union[str, None] = "shared_0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mailbox_sync_cursors",
        sa.Column("mailbox_binding_id", sa.String(length=255), nullable=False),
        sa.Column("folder", sa.String(length=255), nullable=False),
        sa.Column("company_id", sa.String(length=255), nullable=False),
        sa.Column("uidvalidity", sa.BigInteger(), nullable=False),
        sa.Column("last_uid", sa.BigInteger(), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_kind", sa.String(length=32), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_message", sa.String(length=1024), nullable=True),
        sa.PrimaryKeyConstraint("mailbox_binding_id", "folder", name="pk_mailbox_sync_cursors"),
        sa.CheckConstraint(
            "last_error_kind IS NULL OR last_error_kind IN ('auth','network','validation','unknown')",
            name="mailbox_sync_cursors_error_kind_check",
        ),
    )
    op.create_index(
        "ix_mailbox_sync_cursors_company_id",
        "mailbox_sync_cursors",
        ["company_id"],
    )
    op.create_index(
        "ix_mailbox_sync_cursors_last_synced_at",
        "mailbox_sync_cursors",
        ["last_synced_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_mailbox_sync_cursors_last_synced_at", table_name="mailbox_sync_cursors")
    op.drop_index("ix_mailbox_sync_cursors_company_id", table_name="mailbox_sync_cursors")
    op.drop_table("mailbox_sync_cursors")
