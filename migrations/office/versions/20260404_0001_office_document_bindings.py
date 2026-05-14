"""office document bindings

Revision ID: office_0001
Revises:
Create Date: 2026-04-04
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "office_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "office_document_bindings",
        sa.Column("binding_id", sa.String(length=64), nullable=False),
        sa.Column("company_id", sa.String(length=100), nullable=False),
        sa.Column("namespace", sa.String(length=64), nullable=False, server_default="default"),
        sa.Column("file_id", sa.String(length=128), nullable=False),
        sa.Column("document_type", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("binding_id"),
    )
    op.create_index(
        "ix_office_bindings_company_id",
        "office_document_bindings",
        ["company_id"],
        unique=False,
    )
    op.create_index(
        "ix_office_bindings_company_namespace_created",
        "office_document_bindings",
        ["company_id", "namespace", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_office_bindings_company_namespace_created",
        table_name="office_document_bindings",
    )
    op.drop_index("ix_office_bindings_company_id", table_name="office_document_bindings")
    op.drop_table("office_document_bindings")
