"""entity_type_catalog_revision + company-wide list index

Revision ID: 20260815_0028
Revises: 20260811_0027
Create Date: 2026-08-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260815_0028"
down_revision: Union[str, None] = "20260811_0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "entity_type_catalog_revision",
        sa.Column("company_id", sa.String(length=100), nullable=False),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("company_id"),
    )
    op.create_index(
        "ix_entity_types_company_system_type",
        "entity_types",
        ["company_id", sa.text("is_system DESC"), sa.text("type_id ASC")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_entity_types_company_system_type", table_name="entity_types")
    op.drop_table("entity_type_catalog_revision")
