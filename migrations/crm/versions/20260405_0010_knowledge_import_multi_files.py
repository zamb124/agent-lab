"""crm_knowledge_imports: несколько source_file_ids

Revision ID: crm_0010
Revises: crm_0009
Create Date: 2026-04-05
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "crm_0010"
down_revision: Union[str, None] = "crm_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "crm_knowledge_imports",
        sa.Column("source_file_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("crm_knowledge_imports", "source_file_ids")
