"""sync_channel_members.notifications_muted

Revision ID: sync_0004
Revises: sync_0003
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "sync_0004"
down_revision: Union[str, None] = "sync_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
def upgrade() -> None:
    op.add_column(
        "sync_channel_members",
        sa.Column(
            "notifications_muted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.alter_column(
        "sync_channel_members",
        "notifications_muted",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_column("sync_channel_members", "notifications_muted")
