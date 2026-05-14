"""crm_suggests and auto resolve flag

Revision ID: 1045cfb7c721
Revises: crm_0023
Create Date: 2026-05-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "1045cfb7c721"
down_revision: Union[str, None] = "crm_0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "crm_suggests",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("company_id", sa.String(length=100), nullable=False),
        sa.Column("namespace", sa.String(length=100), nullable=False),
        sa.Column("suggest_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("target_entity_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_crm_suggests_company_ns_status",
        "crm_suggests",
        ["company_id", "namespace", "status"],
        unique=False,
    )
    op.create_index("ix_crm_suggests_company_id", "crm_suggests", ["company_id"], unique=False)
    op.create_index("ix_crm_suggests_namespace", "crm_suggests", ["namespace"], unique=False)
    op.create_index("ix_crm_suggests_status", "crm_suggests", ["status"], unique=False)
    op.add_column(
        "entity_types",
        sa.Column(
            "auto_resolve_suggests",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("entity_types", "auto_resolve_suggests")
    op.drop_index("ix_crm_suggests_status", table_name="crm_suggests")
    op.drop_index("ix_crm_suggests_namespace", table_name="crm_suggests")
    op.drop_index("ix_crm_suggests_company_id", table_name="crm_suggests")
    op.drop_index("ix_crm_suggests_company_ns_status", table_name="crm_suggests")
    op.drop_table("crm_suggests")
