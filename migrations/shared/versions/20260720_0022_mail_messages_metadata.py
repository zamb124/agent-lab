"""Mail message metadata for local sync + RAG.

Revision ID: shared_0022
Revises: shared_0021
Create Date: 2026-07-20
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "shared_0022"
down_revision: Union[str, None] = "shared_0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mail_messages",
        sa.Column("mail_message_id", sa.String(length=64), nullable=False),
        sa.Column("company_id", sa.String(length=255), nullable=False),
        sa.Column("mailbox_binding_id", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("folder", sa.String(length=255), nullable=False),
        sa.Column("uid", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.String(length=998), nullable=True),
        sa.Column("thread_id", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False, server_default=""),
        sa.Column("from_address", sa.String(length=998), nullable=False, server_default=""),
        sa.Column("to_addresses", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("cc_addresses", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("date_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unread", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("has_attachments", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("snippet", sa.Text(), nullable=False, server_default=""),
        sa.Column("rag_document_id", sa.String(length=255), nullable=True),
        sa.Column("rag_namespace", sa.String(length=255), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("mail_message_id", name="pk_mail_messages"),
        sa.UniqueConstraint(
            "mailbox_binding_id",
            "folder",
            "uid",
            name="uq_mail_messages_binding_folder_uid",
        ),
    )
    op.create_index("ix_mail_messages_company_id", "mail_messages", ["company_id"])
    op.create_index("ix_mail_messages_user_id", "mail_messages", ["user_id"])
    op.create_index(
        "ix_mail_messages_mailbox_folder_date",
        "mail_messages",
        ["mailbox_binding_id", "folder", "date_at"],
    )
    op.create_index("ix_mail_messages_thread_id", "mail_messages", ["thread_id"])


def downgrade() -> None:
    op.drop_index("ix_mail_messages_thread_id", table_name="mail_messages")
    op.drop_index("ix_mail_messages_mailbox_folder_date", table_name="mail_messages")
    op.drop_index("ix_mail_messages_user_id", table_name="mail_messages")
    op.drop_index("ix_mail_messages_company_id", table_name="mail_messages")
    op.drop_table("mail_messages")
