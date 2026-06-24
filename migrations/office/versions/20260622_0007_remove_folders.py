"""Remove document folders; documents live only in catalogs.

Revision ID: office_0007
Revises: office_0006
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "office_0007"
down_revision: Union[str, None] = "office_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("fk_office_bindings_folder_id", "office_document_bindings", type_="foreignkey")
    op.drop_index(op.f("ix_office_document_bindings_folder_id"), table_name="office_document_bindings")
    op.drop_column("office_document_bindings", "folder_id")
    op.drop_table("office_document_folders")


def downgrade() -> None:
    op.create_table(
        "office_document_folders",
        sa.Column("folder_id", sa.String(length=64), nullable=False),
        sa.Column("company_id", sa.String(length=100), nullable=False),
        sa.Column("namespace", sa.String(length=64), nullable=False),
        sa.Column("catalog_id", sa.String(length=64), nullable=False),
        sa.Column("parent_folder_id", sa.String(length=64), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["catalog_id"], ["office_document_catalogs.catalog_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_folder_id"], ["office_document_folders.folder_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("folder_id"),
    )
    op.create_index("ix_office_folders_catalog_parent", "office_document_folders", ["catalog_id", "parent_folder_id"])
    op.create_index(op.f("ix_office_document_folders_catalog_id"), "office_document_folders", ["catalog_id"])
    op.create_index(op.f("ix_office_document_folders_company_id"), "office_document_folders", ["company_id"])
    op.create_index(op.f("ix_office_document_folders_parent_folder_id"), "office_document_folders", ["parent_folder_id"])
    op.add_column(
        "office_document_bindings",
        sa.Column("folder_id", sa.String(length=64), nullable=True),
    )
    op.create_foreign_key(
        "fk_office_bindings_folder_id",
        "office_document_bindings",
        "office_document_folders",
        ["folder_id"],
        ["folder_id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_office_document_bindings_folder_id"), "office_document_bindings", ["folder_id"])
