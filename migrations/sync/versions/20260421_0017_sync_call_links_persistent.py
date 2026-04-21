"""Постоянная гостевая ссылка на канал: флаг is_persistent_channel_link и уникальность.

Revision ID: sync_0017
Revises: sync_0016
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "sync_0017"
down_revision: Union[str, None] = "sync_0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sync_call_links",
        sa.Column(
            "is_persistent_channel_link",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.execute(
        """
        WITH keepers AS (
            SELECT DISTINCT ON (company_id, channel_id) link_token
            FROM sync_call_links
            WHERE calendar_event_id IS NULL
            ORDER BY company_id, channel_id, expires_at DESC, created_at DESC
        )
        DELETE FROM sync_call_links l
        WHERE l.calendar_event_id IS NULL
        AND l.link_token NOT IN (SELECT link_token FROM keepers)
        """
    )
    op.execute(
        """
        UPDATE sync_call_links
        SET is_persistent_channel_link = true
        WHERE calendar_event_id IS NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_sync_call_links_persistent_channel
        ON sync_call_links (company_id, channel_id)
        WHERE is_persistent_channel_link = true
        """
    )
    op.alter_column(
        "sync_call_links",
        "is_persistent_channel_link",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_index("uq_sync_call_links_persistent_channel", table_name="sync_call_links")
    op.drop_column("sync_call_links", "is_persistent_channel_link")
