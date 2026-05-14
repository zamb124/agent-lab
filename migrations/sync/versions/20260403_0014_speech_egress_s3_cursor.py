"""Курсор S3 для speech-to-chat: не листать весь префикс на каждом тике."""

import sqlalchemy as sa
from alembic import op

revision = "sync_0014"
down_revision = "sync_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sync_call_speech_egress_tracks",
        sa.Column("last_segment_s3_key", sa.String(length=1024), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sync_call_speech_egress_tracks", "last_segment_s3_key")
