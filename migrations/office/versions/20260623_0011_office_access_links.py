"""Public link access fields and binding members.

Revision ID: office_0011
Revises: office_0010
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "office_0011"
down_revision: Union[str, None] = "office_0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "office_document_catalogs",
        sa.Column("link_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "office_document_catalogs",
        sa.Column("link_token_hash", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "office_document_catalogs",
        sa.Column("link_permission", sa.String(length=16), nullable=False, server_default="view"),
    )
    op.add_column(
        "office_document_catalogs",
        sa.Column("link_updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "uq_office_catalogs_link_token_hash",
        "office_document_catalogs",
        ["link_token_hash"],
        unique=True,
        postgresql_where=sa.text("link_token_hash IS NOT NULL"),
    )

    op.add_column(
        "office_document_bindings",
        sa.Column("link_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "office_document_bindings",
        sa.Column("link_token_hash", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "office_document_bindings",
        sa.Column("link_permission", sa.String(length=16), nullable=False, server_default="view"),
    )
    op.add_column(
        "office_document_bindings",
        sa.Column("link_updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "uq_office_bindings_link_token_hash",
        "office_document_bindings",
        ["link_token_hash"],
        unique=True,
        postgresql_where=sa.text("link_token_hash IS NOT NULL"),
    )

    op.create_table(
        "office_binding_members",
        sa.Column("binding_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["binding_id"],
            ["office_document_bindings.binding_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("binding_id", "user_id"),
    )

    op.alter_column("office_document_catalogs", "link_enabled", server_default=None)
    op.alter_column("office_document_catalogs", "link_permission", server_default=None)
    op.alter_column("office_document_bindings", "link_enabled", server_default=None)
    op.alter_column("office_document_bindings", "link_permission", server_default=None)


def downgrade() -> None:
    op.drop_table("office_binding_members")
    op.drop_index("uq_office_bindings_link_token_hash", table_name="office_document_bindings")
    op.drop_column("office_document_bindings", "link_updated_at")
    op.drop_column("office_document_bindings", "link_permission")
    op.drop_column("office_document_bindings", "link_token_hash")
    op.drop_column("office_document_bindings", "link_enabled")
    op.drop_index("uq_office_catalogs_link_token_hash", table_name="office_document_catalogs")
    op.drop_column("office_document_catalogs", "link_updated_at")
    op.drop_column("office_document_catalogs", "link_permission")
    op.drop_column("office_document_catalogs", "link_token_hash")
    op.drop_column("office_document_catalogs", "link_enabled")
