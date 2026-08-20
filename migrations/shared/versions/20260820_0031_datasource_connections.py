"""shared datasource connections and company connector catalog.

Revision ID: shared_0031
Revises: shared_0030
Create Date: 2026-08-20
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "shared_0031"
down_revision: Union[str, None] = "shared_0030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "datasource_connectors",
        sa.Column("company_id", sa.String(length=255), primary_key=True),
        sa.Column("connector_id", sa.String(length=255), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("executor", sa.String(length=32), nullable=False),
        sa.Column("icon", sa.String(length=64), nullable=False),
        sa.Column("credential_schema", JSONB(), nullable=False),
        sa.Column("operations", JSONB(), nullable=False),
        sa.Column("mcp_server_id", sa.String(length=255), nullable=True),
        sa.Column("mcp_introspect_tool", sa.String(length=255), nullable=True),
        sa.Column("mcp_query_tool", sa.String(length=255), nullable=True),
        sa.Column("mcp_execute_tool", sa.String(length=255), nullable=True),
        sa.Column("flow_id", sa.String(length=255), nullable=True),
        sa.Column("flow_branch_id", sa.String(length=255), nullable=False),
        sa.Column("owner_user_id", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "executor IN ('mcp','flow')",
            name="datasource_connectors_executor_check",
        ),
    )
    op.create_index(
        "ix_datasource_connectors_company_id",
        "datasource_connectors",
        ["company_id"],
    )
    op.create_table(
        "datasource_connections",
        sa.Column("datasource_id", sa.String(length=255), primary_key=True),
        sa.Column("company_id", sa.String(length=255), nullable=False),
        sa.Column("connector_id", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("host", sa.String(length=255), nullable=True),
        sa.Column("port", sa.Integer(), nullable=True),
        sa.Column("database_name", sa.String(length=255), nullable=True),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("password_encrypted", sa.Text(), nullable=True),
        sa.Column("ssl_mode", sa.String(length=32), nullable=False),
        sa.Column("allowed_operations", JSONB(), nullable=False),
        sa.Column("statement_timeout_ms", sa.Integer(), nullable=False),
        sa.Column("max_rows", sa.Integer(), nullable=False),
        sa.Column("mcp_server_id", sa.String(length=255), nullable=True),
        sa.Column("flow_id", sa.String(length=255), nullable=True),
        sa.Column("flow_branch_id", sa.String(length=255), nullable=False),
        sa.Column("owner_user_id", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "company_id",
            "name",
            name="uq_datasource_connections_company_name",
        ),
        sa.CheckConstraint(
            "ssl_mode IN ('disable','require','verify-full')",
            name="datasource_connections_ssl_mode_check",
        ),
    )
    op.create_index(
        "ix_datasource_connections_company_id",
        "datasource_connections",
        ["company_id"],
    )
    op.create_index(
        "ix_datasource_connections_company_connector",
        "datasource_connections",
        ["company_id", "connector_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_datasource_connections_company_connector",
        table_name="datasource_connections",
    )
    op.drop_index(
        "ix_datasource_connections_company_id",
        table_name="datasource_connections",
    )
    op.drop_table("datasource_connections")
    op.drop_index(
        "ix_datasource_connectors_company_id",
        table_name="datasource_connectors",
    )
    op.drop_table("datasource_connectors")
