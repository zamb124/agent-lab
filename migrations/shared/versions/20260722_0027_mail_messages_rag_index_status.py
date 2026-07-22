"""mail_messages.rag_index_status for async RAG indexing.

Revision ID: shared_0027
Revises: shared_0026
Create Date: 2026-07-22
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "shared_0027"
down_revision: Union[str, None] = "shared_0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "mail_messages",
        sa.Column(
            "rag_index_status",
            sa.String(length=32),
            nullable=False,
            server_default="skipped",
        ),
    )
    op.execute(
        sa.text(
            "UPDATE mail_messages SET rag_index_status = 'ready' "
            "WHERE rag_document_id IS NOT NULL AND btrim(rag_document_id) <> ''"
        )
    )


def downgrade() -> None:
    op.drop_column("mail_messages", "rag_index_status")
