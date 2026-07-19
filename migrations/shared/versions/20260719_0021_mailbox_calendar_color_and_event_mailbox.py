"""Mailbox calendar_color + calendar_events.mailbox_binding_id.

Revision ID: shared_0021
Revises: shared_0020
Create Date: 2026-07-19
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "shared_0021"
down_revision: Union[str, None] = "shared_0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "mailbox_bindings",
        sa.Column("calendar_color", sa.String(length=32), nullable=False, server_default="default"),
    )
    op.alter_column("mailbox_bindings", "calendar_color", server_default=None)

    op.add_column(
        "calendar_events",
        sa.Column("mailbox_binding_id", sa.String(length=255), nullable=True),
    )
    op.create_index(
        "ix_calendar_events_mailbox_binding_id",
        "calendar_events",
        ["mailbox_binding_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_calendar_events_mailbox_binding_id", table_name="calendar_events")
    op.drop_column("calendar_events", "mailbox_binding_id")
    op.drop_column("mailbox_bindings", "calendar_color")
