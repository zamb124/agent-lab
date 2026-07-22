"""Mail connections: scope company|personal + owner_user_id.

Revision ID: shared_0025
Revises: shared_0024
Create Date: 2026-07-22
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "shared_0025"
down_revision: Union[str, None] = "shared_0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "company_mail_connections",
        sa.Column(
            "scope",
            sa.String(length=32),
            nullable=False,
            server_default="company",
        ),
    )
    op.add_column(
        "company_mail_connections",
        sa.Column("owner_user_id", sa.String(length=255), nullable=True),
    )
    op.create_check_constraint(
        "company_mail_connections_scope_check",
        "company_mail_connections",
        "scope IN ('company','personal')",
    )
    op.create_check_constraint(
        "company_mail_connections_scope_owner_check",
        "company_mail_connections",
        "(scope = 'company' AND owner_user_id IS NULL) OR "
        "(scope = 'personal' AND owner_user_id IS NOT NULL)",
    )
    op.drop_constraint(
        "uq_company_mail_connections_company_id",
        "company_mail_connections",
        type_="unique",
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_company_mail_connections_company_scope "
        "ON company_mail_connections (company_id) "
        "WHERE scope = 'company'"
    )
    op.create_index(
        "ix_company_mail_connections_owner_user_id",
        "company_mail_connections",
        ["owner_user_id"],
    )
    op.alter_column(
        "company_mail_connections",
        "scope",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_company_mail_connections_owner_user_id",
        table_name="company_mail_connections",
    )
    op.execute("DROP INDEX IF EXISTS uq_company_mail_connections_company_scope")
    op.create_unique_constraint(
        "uq_company_mail_connections_company_id",
        "company_mail_connections",
        ["company_id"],
    )
    op.drop_constraint(
        "company_mail_connections_scope_owner_check",
        "company_mail_connections",
        type_="check",
    )
    op.drop_constraint(
        "company_mail_connections_scope_check",
        "company_mail_connections",
        type_="check",
    )
    op.drop_column("company_mail_connections", "owner_user_id")
    op.drop_column("company_mail_connections", "scope")
