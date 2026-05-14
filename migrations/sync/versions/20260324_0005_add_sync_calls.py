"""sync_calls и sync_call_participants — таблицы WebRTC звонков

Revision ID: sync_0005
Revises: sync_0004
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "sync_0005"
down_revision: Union[str, None] = "sync_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sync_calls",
        sa.Column("call_id", sa.String(64), primary_key=True),
        sa.Column("company_id", sa.String(100), nullable=False),
        sa.Column(
            "channel_id",
            sa.String(64),
            sa.ForeignKey("sync_channels.channel_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("mode", sa.String(8), nullable=False),
        sa.Column("call_type", sa.String(8), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="ringing"),
        sa.Column("livekit_room_name", sa.String(128), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("created_by_user_id", sa.String(64), nullable=False),
    )
    op.create_index("ix_sync_calls_company", "sync_calls", ["company_id"])
    op.create_index("ix_sync_calls_channel", "sync_calls", ["channel_id"])
    op.create_index("ix_sync_calls_status", "sync_calls", ["status"])

    op.create_table(
        "sync_call_participants",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "call_id",
            sa.String(64),
            sa.ForeignKey("sync_calls.call_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="invited"),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("call_id", "user_id", name="uq_sync_call_participant"),
    )
    op.create_index("ix_sync_call_participants_call", "sync_call_participants", ["call_id"])
    op.create_index("ix_sync_call_participants_user", "sync_call_participants", ["user_id"])


def downgrade() -> None:
    op.drop_table("sync_call_participants")
    op.drop_table("sync_calls")
