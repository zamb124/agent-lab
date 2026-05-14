"""platform_short_links для коротких URL (Sync join, инвайты).

Revision ID: shared_0005
Revises: shared_0004
Create Date: 2026-04-05
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "shared_0005"
down_revision: Union[str, None] = "shared_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "platform_short_links",
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("code", name=op.f("pk_platform_short_links")),
    )
    op.create_index(op.f("ix_platform_short_links_expires_at"), "platform_short_links", ["expires_at"], unique=False)
    op.create_index(op.f("ix_platform_short_links_kind"), "platform_short_links", ["kind"], unique=False)
    op.create_index(
        "ix_platform_short_links_sync_link_token",
        "platform_short_links",
        [sa.text("(payload->>'link_token')")],
        unique=False,
        postgresql_where=sa.text("kind = 'sync_call_join'"),
    )


def downgrade() -> None:
    op.drop_index("ix_platform_short_links_sync_link_token", table_name="platform_short_links")
    op.drop_index(op.f("ix_platform_short_links_kind"), table_name="platform_short_links")
    op.drop_index(op.f("ix_platform_short_links_expires_at"), table_name="platform_short_links")
    op.drop_table("platform_short_links")
