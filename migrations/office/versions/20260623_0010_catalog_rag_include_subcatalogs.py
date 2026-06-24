"""Catalog RAG include subcatalogs flag.

Revision ID: office_0010
Revises: office_0009
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "office_0010"
down_revision: Union[str, None] = "office_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "office_document_catalogs",
        sa.Column(
            "rag_index_include_subcatalogs",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.alter_column("office_document_catalogs", "rag_index_include_subcatalogs", server_default=None)


def downgrade() -> None:
    op.drop_column("office_document_catalogs", "rag_index_include_subcatalogs")
