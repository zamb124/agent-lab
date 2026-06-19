"""runet gpu relief: disable rerank and shrink retrieval pool

Revision ID: search_0011
Revises: search_0010
Create Date: 2026-06-19
"""

from typing import Sequence, Union

from alembic import op

revision: str = "search_0011"
down_revision: Union[str, None] = "search_0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE search_indexes
        SET retrieval_rerank = false,
            retrieval_per_channel_top_k = 50,
            updated_at = NOW()
        WHERE search_index_id = 'runet'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE search_indexes
        SET retrieval_rerank = true,
            retrieval_per_channel_top_k = 150,
            updated_at = NOW()
        WHERE search_index_id = 'runet'
        """
    )
