"""Documents file manager: trash, folders, shares, revisions, activity.

Revision ID: office_0005
Revises: office_0004
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "office_0005"
down_revision: Union[str, None] = "office_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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
    op.add_column(
        "office_document_bindings",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "office_document_bindings",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "office_document_bindings",
        sa.Column("deleted_by_user_id", sa.String(length=100), nullable=True),
    )
    op.execute(
        """
        UPDATE office_document_bindings
        SET updated_at = created_at
        WHERE updated_at IS NULL
        """
    )
    op.alter_column("office_document_bindings", "updated_at", nullable=False)
    op.create_foreign_key(
        "fk_office_bindings_folder_id",
        "office_document_bindings",
        "office_document_folders",
        ["folder_id"],
        ["folder_id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_office_document_bindings_folder_id"), "office_document_bindings", ["folder_id"])
    op.create_index("ix_office_bindings_deleted_at", "office_document_bindings", ["company_id", "namespace", "deleted_at"])

    op.create_table(
        "office_document_shares",
        sa.Column("share_id", sa.String(length=64), nullable=False),
        sa.Column("binding_id", sa.String(length=64), nullable=False),
        sa.Column("company_id", sa.String(length=100), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=100), nullable=False),
        sa.Column("permission", sa.String(length=16), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["binding_id"], ["office_document_bindings.binding_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("share_id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(op.f("ix_office_document_shares_binding_id"), "office_document_shares", ["binding_id"])
    op.create_index(op.f("ix_office_document_shares_company_id"), "office_document_shares", ["company_id"])

    op.create_table(
        "office_document_revisions",
        sa.Column("revision_id", sa.String(length=64), nullable=False),
        sa.Column("binding_id", sa.String(length=64), nullable=False),
        sa.Column("file_id", sa.String(length=128), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["binding_id"], ["office_document_bindings.binding_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("revision_id"),
    )
    op.create_index("ix_office_revisions_binding_number", "office_document_revisions", ["binding_id", "revision_number"])
    op.create_index(op.f("ix_office_document_revisions_binding_id"), "office_document_revisions", ["binding_id"])

    op.create_table(
        "office_document_events",
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("binding_id", sa.String(length=64), nullable=False),
        sa.Column("company_id", sa.String(length=100), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=100), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["binding_id"], ["office_document_bindings.binding_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index(op.f("ix_office_document_events_binding_id"), "office_document_events", ["binding_id"])
    op.create_index(op.f("ix_office_document_events_company_id"), "office_document_events", ["company_id"])


def downgrade() -> None:
    op.drop_table("office_document_events")
    op.drop_table("office_document_revisions")
    op.drop_table("office_document_shares")
    op.drop_index("ix_office_bindings_deleted_at", table_name="office_document_bindings")
    op.drop_constraint("fk_office_bindings_folder_id", "office_document_bindings", type_="foreignkey")
    op.drop_index(op.f("ix_office_document_bindings_folder_id"), table_name="office_document_bindings")
    op.drop_column("office_document_bindings", "deleted_by_user_id")
    op.drop_column("office_document_bindings", "deleted_at")
    op.drop_column("office_document_bindings", "updated_at")
    op.drop_column("office_document_bindings", "folder_id")
    op.drop_table("office_document_folders")
