"""flow_ui_share_grants.permission canon: viewer | editor

Revision ID: 20260811_0033
Revises: 20260805_0032
Create Date: 2026-08-11
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20260811_0033"
down_revision: Union[str, None] = "20260805_0032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE flow_ui_share_grants SET permission = 'viewer' "
        "WHERE permission = 'view'"
    )
    op.execute(
        "UPDATE flow_ui_share_grants SET permission = 'editor' "
        "WHERE permission = 'interact'"
    )


def downgrade() -> None:
    raise NotImplementedError(
        "20260811_0033 downgrade is not supported; reset DB and upgrade head"
    )
