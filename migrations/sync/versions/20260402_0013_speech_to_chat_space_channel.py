"""Речь в ленту: флаги space/channel, трекинг egress по микрофону LiveKit."""

from alembic import op
import sqlalchemy as sa

revision = "sync_0013"
down_revision = "sync_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sync_spaces",
        sa.Column("transcribe_voice_messages", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "sync_spaces",
        sa.Column("speech_to_chat_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("sync_spaces", "transcribe_voice_messages", server_default=None)
    op.alter_column("sync_spaces", "speech_to_chat_enabled", server_default=None)

    op.add_column(
        "sync_channels",
        sa.Column("speech_to_chat_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("sync_channels", "speech_to_chat_enabled", server_default=None)

    op.create_table(
        "sync_call_speech_egress_tracks",
        sa.Column("row_id", sa.String(length=64), nullable=False),
        sa.Column("call_id", sa.String(length=64), nullable=False),
        sa.Column("company_id", sa.String(length=100), nullable=False),
        sa.Column("channel_id", sa.String(length=64), nullable=False),
        sa.Column("participant_identity", sa.String(length=200), nullable=False),
        sa.Column("track_sid", sa.String(length=128), nullable=False),
        sa.Column("egress_id", sa.String(length=128), nullable=False),
        sa.Column("segments_posted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["call_id"], ["sync_calls.call_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["channel_id"], ["sync_channels.channel_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("row_id"),
        sa.UniqueConstraint("call_id", "track_sid", name="uq_sync_call_speech_track"),
        sa.UniqueConstraint("egress_id", name="uq_sync_call_speech_egress_id"),
    )
    op.create_index(
        "ix_sync_call_speech_egress_tracks_call",
        "sync_call_speech_egress_tracks",
        ["call_id"],
        unique=False,
    )
    op.create_index(
        "ix_sync_call_speech_egress_tracks_company",
        "sync_call_speech_egress_tracks",
        ["company_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_sync_call_speech_egress_tracks_company", table_name="sync_call_speech_egress_tracks")
    op.drop_index("ix_sync_call_speech_egress_tracks_call", table_name="sync_call_speech_egress_tracks")
    op.drop_table("sync_call_speech_egress_tracks")

    op.drop_column("sync_channels", "speech_to_chat_enabled")

    op.drop_column("sync_spaces", "speech_to_chat_enabled")
    op.drop_column("sync_spaces", "transcribe_voice_messages")
