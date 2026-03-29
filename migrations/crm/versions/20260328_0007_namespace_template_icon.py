"""crm namespace template icon

Revision ID: crm_0007
Revises: crm_0006
Create Date: 2026-03-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "crm_0007"
down_revision: Union[str, None] = "crm_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("namespace_templates", sa.Column("icon", sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column("namespace_templates", "icon")
