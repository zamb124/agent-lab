"""sync_call_links — гостевые ссылки на звонки

Revision ID: sync_0006
Revises: sync_0005
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "sync_0006"
down_revision: Union[str, None] = "sync_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sync_call_links",
        sa.Column("link_token", sa.String(64), primary_key=True),
        sa.Column(
            "channel_id",
            sa.String(64),
            sa.ForeignKey("sync_channels.channel_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("company_id", sa.String(100), nullable=False),
        sa.Column(
            "call_id",
            sa.String(64),
            sa.ForeignKey("sync_calls.call_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("call_type", sa.String(8), nullable=False, server_default="video"),
        sa.Column("created_by_user_id", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_sync_call_links_channel", "sync_call_links", ["channel_id"])
    op.create_index("ix_sync_call_links_company", "sync_call_links", ["company_id"])
    op.create_index("ix_sync_call_links_expires", "sync_call_links", ["expires_at"])


def downgrade() -> None:
    op.drop_table("sync_call_links")
