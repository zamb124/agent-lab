"""Mail local-first: folder cache + message bodies/attachments.

Revision ID: shared_0023
Revises: shared_0022
Create Date: 2026-07-20
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "shared_0023"
down_revision: Union[str, None] = "shared_0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mailbox_folders",
        sa.Column("mailbox_binding_id", sa.String(length=255), nullable=False),
        sa.Column("folder_name", sa.String(length=255), nullable=False),
        sa.Column("company_id", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False, server_default="other"),
        sa.Column("delimiter", sa.String(length=16), nullable=True),
        sa.Column("flags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("selectable", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unseen_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("namespace_prefix", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("capabilities", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "mailbox_binding_id",
            "folder_name",
            name="pk_mailbox_folders",
        ),
    )
    op.create_index("ix_mailbox_folders_company_id", "mailbox_folders", ["company_id"])

    op.add_column("mail_messages", sa.Column("body_text", sa.Text(), nullable=True))
    op.add_column("mail_messages", sa.Column("body_html", sa.Text(), nullable=True))
    op.add_column(
        "mail_messages",
        sa.Column(
            "attachments_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "mail_messages",
        sa.Column("in_reply_to", sa.String(length=998), nullable=True),
    )
    op.add_column(
        "mail_messages",
        sa.Column("references_header", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("mail_messages", "references_header")
    op.drop_column("mail_messages", "in_reply_to")
    op.drop_column("mail_messages", "attachments_json")
    op.drop_column("mail_messages", "body_html")
    op.drop_column("mail_messages", "body_text")
    op.drop_index("ix_mailbox_folders_company_id", table_name="mailbox_folders")
    op.drop_table("mailbox_folders")
