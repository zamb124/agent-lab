"""Канал-only STT: убрать встречи/сегменты, колонки space, call_id и авто-STT на канале."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "sync_0012"
down_revision = "sync_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_sync_call_speaker_segments_identity", table_name="sync_call_speaker_segments")
    op.drop_index("ix_sync_call_speaker_segments_meeting", table_name="sync_call_speaker_segments")
    op.drop_index("ix_sync_call_speaker_segments_company", table_name="sync_call_speaker_segments")
    op.drop_table("sync_call_speaker_segments")

    op.drop_index("ix_sync_call_meetings_space", table_name="sync_call_meetings")
    op.drop_index("ix_sync_call_meetings_channel", table_name="sync_call_meetings")
    op.drop_index("ix_sync_call_meetings_call", table_name="sync_call_meetings")
    op.drop_index("ix_sync_call_meetings_company", table_name="sync_call_meetings")
    op.drop_table("sync_call_meetings")

    op.drop_column("sync_spaces", "auto_export_summary_to_crm")
    op.drop_column("sync_spaces", "auto_export_transcript_to_crm")

    op.add_column(
        "sync_channels",
        sa.Column("transcribe_voice_messages", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("sync_channels", "transcribe_voice_messages", server_default=None)

    op.alter_column(
        "sync_messages",
        "sender_user_id",
        existing_type=sa.String(length=64),
        type_=sa.String(length=200),
        existing_nullable=False,
    )

    op.add_column(
        "sync_messages",
        sa.Column("call_id", sa.String(length=64), nullable=True),
    )
    op.create_foreign_key(
        "fk_sync_messages_call_id",
        "sync_messages",
        "sync_calls",
        ["call_id"],
        ["call_id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_sync_messages_call_id", "sync_messages", ["call_id"], unique=False)
    op.create_index(
        "ix_sync_messages_channel_call",
        "sync_messages",
        ["channel_id", "call_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_sync_messages_channel_call", table_name="sync_messages")
    op.drop_index("ix_sync_messages_call_id", table_name="sync_messages")
    op.drop_constraint("fk_sync_messages_call_id", "sync_messages", type_="foreignkey")
    op.drop_column("sync_messages", "call_id")

    op.alter_column(
        "sync_messages",
        "sender_user_id",
        existing_type=sa.String(length=200),
        type_=sa.String(length=64),
        existing_nullable=False,
    )

    op.drop_column("sync_channels", "transcribe_voice_messages")

    op.add_column(
        "sync_spaces",
        sa.Column("auto_export_transcript_to_crm", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "sync_spaces",
        sa.Column("auto_export_summary_to_crm", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("sync_spaces", "auto_export_transcript_to_crm", server_default=None)
    op.alter_column("sync_spaces", "auto_export_summary_to_crm", server_default=None)

    op.create_table(
        "sync_call_meetings",
        sa.Column("meeting_id", sa.String(length=64), nullable=False),
        sa.Column("call_id", sa.String(length=64), nullable=False),
        sa.Column("recording_id", sa.String(length=64), nullable=True),
        sa.Column("company_id", sa.String(length=100), nullable=False),
        sa.Column("channel_id", sa.String(length=64), nullable=False),
        sa.Column("space_id", sa.String(length=64), nullable=True),
        sa.Column("transcript_file_id", sa.String(length=64), nullable=True),
        sa.Column("transcript_text_file_id", sa.String(length=64), nullable=True),
        sa.Column("summary_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("export_status", sa.String(length=24), nullable=False),
        sa.Column("export_target_namespace", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["call_id"], ["sync_calls.call_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recording_id"], ["sync_call_recordings.recording_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["channel_id"], ["sync_channels.channel_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["space_id"], ["sync_spaces.space_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["transcript_file_id"], ["sync_files.file_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["transcript_text_file_id"], ["sync_files.file_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("meeting_id"),
    )
    op.create_index("ix_sync_call_meetings_company", "sync_call_meetings", ["company_id"], unique=False)
    op.create_index("ix_sync_call_meetings_call", "sync_call_meetings", ["call_id"], unique=False)
    op.create_index("ix_sync_call_meetings_channel", "sync_call_meetings", ["channel_id"], unique=False)
    op.create_index("ix_sync_call_meetings_space", "sync_call_meetings", ["space_id"], unique=False)

    op.create_table(
        "sync_call_speaker_segments",
        sa.Column("segment_id", sa.String(length=64), nullable=False),
        sa.Column("meeting_id", sa.String(length=64), nullable=False),
        sa.Column("company_id", sa.String(length=100), nullable=False),
        sa.Column("speaker_identity", sa.String(length=128), nullable=False),
        sa.Column("speaker_type", sa.String(length=16), nullable=False),
        sa.Column("speaker_user_id", sa.String(length=64), nullable=True),
        sa.Column("speaker_guest_name", sa.String(length=255), nullable=True),
        sa.Column("started_ms", sa.Integer(), nullable=False),
        sa.Column("ended_ms", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["meeting_id"], ["sync_call_meetings.meeting_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("segment_id"),
    )
    op.create_index(
        "ix_sync_call_speaker_segments_company", "sync_call_speaker_segments", ["company_id"], unique=False
    )
    op.create_index(
        "ix_sync_call_speaker_segments_meeting", "sync_call_speaker_segments", ["meeting_id"], unique=False
    )
    op.create_index(
        "ix_sync_call_speaker_segments_identity", "sync_call_speaker_segments", ["speaker_identity"], unique=False
    )
