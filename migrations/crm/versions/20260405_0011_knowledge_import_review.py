"""crm_knowledge_imports: подтверждение просмотра импорта (review_completed_at)

Revision ID: crm_0011
Revises: crm_0010
Create Date: 2026-04-05
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "crm_0011"
down_revision: Union[str, None] = "crm_0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "crm_knowledge_imports",
        sa.Column("review_completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        """
        UPDATE crm_knowledge_imports
        SET review_completed_at = COALESCE(completed_at, created_at)
        WHERE review_completed_at IS NULL
          AND status IN ('completed', 'failed', 'cancelled')
          AND (
            jsonb_array_length(COALESCE(created_entity_ids, '[]'::jsonb)) > 0
            OR jsonb_array_length(COALESCE(created_relationship_ids, '[]'::jsonb)) > 0
          )
        """
    )


def downgrade() -> None:
    op.drop_column("crm_knowledge_imports", "review_completed_at")
