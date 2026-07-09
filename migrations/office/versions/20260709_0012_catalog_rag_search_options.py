"""Catalog RAG per-catalog search_options JSONB.

Revision ID: office_0012
Revises: office_0011
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "office_0012"
down_revision: Union[str, None] = "office_0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "office_document_catalogs",
        sa.Column("rag_index_search_options", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("office_document_catalogs", "rag_index_search_options")
