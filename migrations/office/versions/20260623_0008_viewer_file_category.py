"""Binding file_category + onlyoffice_document_type.

Revision ID: office_0008
Revises: office_0007
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "office_0008"
down_revision: Union[str, None] = "office_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "office_document_bindings",
        sa.Column("file_category", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "office_document_bindings",
        sa.Column("onlyoffice_document_type", sa.String(length=16), nullable=True),
    )
    op.execute(
        """
        UPDATE office_document_bindings
        SET file_category = CASE document_type
            WHEN 'word' THEN 'office_doc'
            WHEN 'cell' THEN 'spreadsheet'
            WHEN 'slide' THEN 'presentation'
            ELSE document_type
        END,
        onlyoffice_document_type = CASE document_type
            WHEN 'word' THEN 'word'
            WHEN 'cell' THEN 'cell'
            WHEN 'slide' THEN 'slide'
            ELSE NULL
        END
        """
    )
    op.alter_column("office_document_bindings", "file_category", nullable=False)
    op.drop_column("office_document_bindings", "document_type")


def downgrade() -> None:
    op.add_column(
        "office_document_bindings",
        sa.Column("document_type", sa.String(length=16), nullable=True),
    )
    op.execute(
        """
        UPDATE office_document_bindings
        SET document_type = COALESCE(
            onlyoffice_document_type,
            CASE file_category
                WHEN 'office_doc' THEN 'word'
                WHEN 'spreadsheet' THEN 'cell'
                WHEN 'presentation' THEN 'slide'
                ELSE 'word'
            END
        )
        """
    )
    op.alter_column("office_document_bindings", "document_type", nullable=False)
    op.drop_column("office_document_bindings", "onlyoffice_document_type")
    op.drop_column("office_document_bindings", "file_category")
