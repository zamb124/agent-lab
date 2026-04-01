"""Календарные поля у гостевых ссылок и индекс по calendar_event_id."""

from alembic import op
import sqlalchemy as sa

revision = "sync_0011"
down_revision = "sync_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sync_call_links",
        sa.Column("title", sa.Text(), nullable=True),
    )
    op.add_column(
        "sync_call_links",
        sa.Column("scheduled_start_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "sync_call_links",
        sa.Column("scheduled_end_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "sync_call_links",
        sa.Column("calendar_event_id", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_sync_call_links_calendar_event_id",
        "sync_call_links",
        ["calendar_event_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_sync_call_links_calendar_event_id", table_name="sync_call_links")
    op.drop_column("sync_call_links", "calendar_event_id")
    op.drop_column("sync_call_links", "scheduled_end_at")
    op.drop_column("sync_call_links", "scheduled_start_at")
    op.drop_column("sync_call_links", "title")
