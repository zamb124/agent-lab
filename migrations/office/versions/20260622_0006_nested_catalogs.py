"""Nested document catalogs via parent_catalog_id.

Revision ID: office_0006
Revises: office_0005
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "office_0006"
down_revision: Union[str, None] = "office_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "office_document_catalogs",
        sa.Column("parent_catalog_id", sa.String(length=64), nullable=True),
    )
    op.create_foreign_key(
        "fk_office_catalogs_parent_catalog_id",
        "office_document_catalogs",
        "office_document_catalogs",
        ["parent_catalog_id"],
        ["catalog_id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_office_catalogs_company_namespace_parent",
        "office_document_catalogs",
        ["company_id", "namespace", "parent_catalog_id"],
    )
    op.create_index(
        op.f("ix_office_document_catalogs_parent_catalog_id"),
        "office_document_catalogs",
        ["parent_catalog_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_office_document_catalogs_parent_catalog_id"), table_name="office_document_catalogs")
    op.drop_index("ix_office_catalogs_company_namespace_parent", table_name="office_document_catalogs")
    op.drop_constraint("fk_office_catalogs_parent_catalog_id", "office_document_catalogs", type_="foreignkey")
    op.drop_column("office_document_catalogs", "parent_catalog_id")
