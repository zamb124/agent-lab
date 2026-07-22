"""mailbox_folders.sort_index for UI folder order.

Revision ID: shared_0026
Revises: shared_0025
Create Date: 2026-07-22
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "shared_0026"
down_revision: Union[str, None] = "shared_0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "mailbox_folders",
        sa.Column(
            "sort_index",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("mailbox_folders", "sort_index")
