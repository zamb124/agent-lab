"""Catalog RAG index flags.

Revision ID: office_0009
Revises: office_0008
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "office_0009"
down_revision: Union[str, None] = "office_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "office_document_catalogs",
        sa.Column("rag_index_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "office_document_catalogs",
        sa.Column("rag_index_updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.alter_column("office_document_catalogs", "rag_index_enabled", server_default=None)


def downgrade() -> None:
    op.drop_column("office_document_catalogs", "rag_index_updated_at")
    op.drop_column("office_document_catalogs", "rag_index_enabled")
