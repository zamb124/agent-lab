"""Baseline sync DB

Revision ID: sync_0001
Revises:
Create Date: 2026-03-20
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "sync_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sync_spaces",
        sa.Column("space_id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("company_id", sa.String(100), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.String(64), nullable=False),
    )
    op.create_index("ix_sync_spaces_company", "sync_spaces", ["company_id"])

    op.create_table(
        "sync_channels",
        sa.Column("channel_id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("company_id", sa.String(100), nullable=False),
        sa.Column("space_id", sa.String(64), sa.ForeignKey("sync_spaces.space_id"), nullable=True),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("is_private", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.String(64), nullable=False),
        sa.Column("pinned_message_ids", postgresql.JSONB(), nullable=False),
    )
    op.create_index("ix_sync_channels_company", "sync_channels", ["company_id"])
    op.create_index("ix_sync_channels_space", "sync_channels", ["space_id"])

    op.create_table(
        "sync_files",
        sa.Column("file_id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("company_id", sa.String(100), nullable=False),
        sa.Column("original_name", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(255), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("storage_url", sa.Text(), nullable=False),
        sa.Column("checksum", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_sync_files_company", "sync_files", ["company_id"])

    op.create_table(
        "sync_threads",
        sa.Column("thread_id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("company_id", sa.String(100), nullable=False),
        sa.Column("channel_id", sa.String(64), sa.ForeignKey("sync_channels.channel_id", ondelete="CASCADE"), nullable=False),
        sa.Column("root_message_id", sa.String(64), nullable=False),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.String(64), nullable=False),
    )
    op.create_index("ix_sync_threads_company", "sync_threads", ["company_id"])
    op.create_index("ix_sync_threads_channel", "sync_threads", ["channel_id"])

    op.create_table(
        "sync_messages",
        sa.Column("message_id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("company_id", sa.String(100), nullable=False),
        sa.Column("channel_id", sa.String(64), sa.ForeignKey("sync_channels.channel_id", ondelete="CASCADE"), nullable=False),
        sa.Column("thread_id", sa.String(64), sa.ForeignKey("sync_threads.thread_id", ondelete="SET NULL"), nullable=True),
        sa.Column("parent_message_id", sa.String(64), sa.ForeignKey("sync_messages.message_id", ondelete="SET NULL"), nullable=True),
        sa.Column("sender_user_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reactions", postgresql.JSONB(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("forwarded_from_channel_id", sa.String(64), nullable=True),
        sa.Column("forwarded_from_channel_name", sa.String(255), nullable=True),
    )
    op.create_index("ix_sync_messages_company", "sync_messages", ["company_id"])
    op.create_index("ix_sync_messages_channel", "sync_messages", ["channel_id"])
    op.create_index("ix_sync_messages_thread", "sync_messages", ["thread_id"])
    op.create_index("ix_sync_messages_sent_at", "sync_messages", ["sent_at"])

    op.create_table(
        "sync_channel_members",
        sa.Column("channel_id", sa.String(64), sa.ForeignKey("sync_channels.channel_id", ondelete="CASCADE"), primary_key=True, nullable=False),
        sa.Column("user_id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("company_id", sa.String(100), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("last_read_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_sync_channel_members_company", "sync_channel_members", ["company_id"])

    op.create_table(
        "sync_message_contents",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("message_id", sa.String(64), sa.ForeignKey("sync_messages.message_id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(64), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=False),
    )
    op.create_index("ix_sync_message_contents_message", "sync_message_contents", ["message_id"])

    op.create_table(
        "sync_message_files",
        sa.Column("message_id", sa.String(64), sa.ForeignKey("sync_messages.message_id", ondelete="CASCADE"), primary_key=True, nullable=False),
        sa.Column("file_id", sa.String(64), sa.ForeignKey("sync_files.file_id", ondelete="CASCADE"), primary_key=True, nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
    )

    op.create_table(
        "sync_git_resource_refs",
        sa.Column("git_ref_id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("company_id", sa.String(100), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("project_key", sa.String(255), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("extra", postgresql.JSONB(), nullable=False),
    )
    op.create_index("ix_sync_git_refs_company", "sync_git_resource_refs", ["company_id"])
    op.create_index("ix_sync_git_refs_provider_kind", "sync_git_resource_refs", ["provider", "kind"])


def downgrade() -> None:
    op.drop_table("sync_git_resource_refs")
    op.drop_table("sync_message_files")
    op.drop_table("sync_message_contents")
    op.drop_table("sync_channel_members")
    op.drop_table("sync_messages")
    op.drop_table("sync_threads")
    op.drop_table("sync_files")
    op.drop_table("sync_channels")
    op.drop_table("sync_spaces")
