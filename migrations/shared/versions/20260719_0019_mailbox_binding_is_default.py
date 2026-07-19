"""Add is_default to mailbox_bindings.

Revision ID: shared_0019
Revises: shared_0018
Create Date: 2026-07-19
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "shared_0019"
down_revision: Union[str, None] = "shared_0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "mailbox_bindings",
        sa.Column(
            "is_default",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_index(
        "ix_mailbox_bindings_user_default",
        "mailbox_bindings",
        ["company_id", "user_id", "is_default"],
    )


def downgrade() -> None:
    op.drop_index("ix_mailbox_bindings_user_default", table_name="mailbox_bindings")
    op.drop_column("mailbox_bindings", "is_default")
