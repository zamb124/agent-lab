"""Add missing branch_id on flow_ui_share_grants."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260804_0031"
down_revision: Union[str, None] = "20260804_0030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("flow_ui_share_grants")}
    if "branch_id" in columns:
        return
    op.add_column(
        "flow_ui_share_grants",
        sa.Column("branch_id", sa.String(), nullable=False, server_default="default"),
    )
    op.alter_column("flow_ui_share_grants", "branch_id", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("flow_ui_share_grants")}
    if "branch_id" not in columns:
        return
    op.drop_column("flow_ui_share_grants", "branch_id")
