"""entity_types: namespace_ids whitelist for namespaces

Revision ID: crm_0004
Revises: crm_0003
Create Date: 2026-03-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "crm_0004"
down_revision: Union[str, None] = "crm_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "entity_types",
        sa.Column(
            "namespace_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[\"default\"]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("entity_types", "namespace_ids")
