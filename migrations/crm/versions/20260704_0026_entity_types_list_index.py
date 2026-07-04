"""entity_types: index for list_by_company sort (company_id, namespace, is_system DESC, type_id ASC)

Revision ID: 20260704_0026
Revises: 20260622_0025
Create Date: 2026-07-04
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260704_0026"
down_revision: Union[str, None] = "20260622_0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_entity_types_company_ns_system_type",
        "entity_types",
        ["company_id", "namespace", sa.text("is_system DESC"), sa.text("type_id ASC")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_entity_types_company_ns_system_type", table_name="entity_types")
