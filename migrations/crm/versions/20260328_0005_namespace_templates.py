"""crm namespace templates tables

Revision ID: crm_0005
Revises: crm_0004
Create Date: 2026-03-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "crm_0005"
down_revision: Union[str, None] = "crm_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "namespace_templates",
        sa.Column("template_key", sa.String(length=100), nullable=False),
        sa.Column("company_id", sa.String(length=100), nullable=False),
        sa.Column("template_id", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("template_key"),
        sa.UniqueConstraint("company_id", "template_id", name="uq_namespace_template_company"),
    )
    op.create_index("ix_namespace_templates_company_id", "namespace_templates", ["company_id"], unique=False)
    op.create_index(
        "idx_namespace_template_company_system",
        "namespace_templates",
        ["company_id", "is_system"],
        unique=False,
    )

    op.create_table(
        "namespace_template_types",
        sa.Column("entry_id", sa.String(length=100), nullable=False),
        sa.Column("template_key", sa.String(length=100), nullable=False),
        sa.Column("type_id", sa.String(length=100), nullable=False),
        sa.Column("parent_type_id", sa.String(length=100), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("required_fields", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("optional_fields", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("icon", sa.String(length=50), nullable=True),
        sa.Column("color", sa.String(length=20), nullable=True),
        sa.Column("is_event", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("check_duplicates", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("weight_coefficient", sa.Float(), nullable=False, server_default=sa.text("1.0")),
        sa.Column("namespace_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["template_key"], ["namespace_templates.template_key"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("entry_id"),
        sa.UniqueConstraint("template_key", "type_id", name="uq_namespace_template_type"),
    )
    op.create_index(
        "ix_namespace_template_types_template_key",
        "namespace_template_types",
        ["template_key"],
        unique=False,
    )
    op.create_index(
        "ix_namespace_template_types_type_id",
        "namespace_template_types",
        ["type_id"],
        unique=False,
    )
    op.create_index(
        "idx_namespace_template_type_template",
        "namespace_template_types",
        ["template_key"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("namespace_template_types")
    op.drop_table("namespace_templates")
