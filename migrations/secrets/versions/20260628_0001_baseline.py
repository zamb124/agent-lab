"""Базовая миграция БД platform_secrets (переменные и секреты компании)

Revision ID: secrets_0001
Revises:
Create Date: 2026-06-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "secrets_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "secret_variables",
        sa.Column("company_id", sa.String(100), primary_key=True, nullable=False),
        sa.Column("variable_key", sa.String(255), primary_key=True, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("secret", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "shared_for_execution",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("public", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_by", sa.String(100), nullable=True),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("order_index", sa.Integer(), nullable=True),
        sa.Column("groups", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("value_payload", postgresql.JSONB(), nullable=True),
        sa.Column("value_encrypted", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_secret_variables_company", "secret_variables", ["company_id"])

    op.create_table(
        "secret_variable_versions",
        sa.Column("company_id", sa.String(100), primary_key=True, nullable=False),
        sa.Column("variable_key", sa.String(255), primary_key=True, nullable=False),
        sa.Column("version", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("secret", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "shared_for_execution",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("public", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_by", sa.String(100), nullable=True),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("order_index", sa.Integer(), nullable=True),
        sa.Column("groups", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("value_payload", postgresql.JSONB(), nullable=True),
        sa.Column("value_encrypted", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_secret_variable_versions_company", "secret_variable_versions", ["company_id"]
    )


def downgrade() -> None:
    op.drop_table("secret_variable_versions")
    op.drop_table("secret_variables")
