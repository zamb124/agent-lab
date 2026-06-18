"""runet retrieval pool defaults

Revision ID: search_0010
Revises: search_0009
Create Date: 2026-06-18
"""

from typing import Sequence, Union

from alembic import op

revision: str = "search_0010"
down_revision: Union[str, None] = "search_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE search_indexes
        SET retrieval_per_channel_top_k = 150
        WHERE search_index_id = 'runet'
          AND retrieval_per_channel_top_k IS NULL
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE search_indexes
        SET retrieval_per_channel_top_k = NULL
        WHERE search_index_id = 'runet'
          AND retrieval_per_channel_top_k = 150
        """
    )
