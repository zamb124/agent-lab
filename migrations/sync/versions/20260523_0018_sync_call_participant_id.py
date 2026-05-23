"""Переименовать id участника звонка в call_participant_id.

Revision ID: sync_0018
Revises: sync_0017
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "sync_0018"
down_revision: Union[str, None] = "sync_0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "sync_call_participants",
        "id",
        new_column_name="call_participant_id",
        existing_type=sa.String(length=64),
    )


def downgrade() -> None:
    op.alter_column(
        "sync_call_participants",
        "call_participant_id",
        new_column_name="id",
        existing_type=sa.String(length=64),
    )
