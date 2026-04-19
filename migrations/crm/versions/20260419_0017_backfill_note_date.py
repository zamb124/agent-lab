"""backfill note_date для заметок без даты

Revision ID: crm_0017
Revises: crm_0016
Create Date: 2026-04-19
"""

from typing import Sequence, Union

from alembic import op

revision: str = "crm_0017"
down_revision: Union[str, None] = "crm_0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE crm_entities
        SET note_date = COALESCE(
            NULLIF(attributes->>'note_date', '')::date,
            (created_at AT TIME ZONE 'UTC')::date
        )
        WHERE entity_type = 'note' AND note_date IS NULL
        """
    )


def downgrade() -> None:
    pass
