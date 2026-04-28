"""crm namespace_templates.crm_settings JSONB

Revision ID: crm_0018
Revises: crm_0017
Create Date: 2026-04-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "crm_0018"
down_revision: Union[str, None] = "crm_0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "namespace_templates",
        sa.Column("crm_settings", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("namespace_templates", "crm_settings")
