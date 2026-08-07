"""Add redacted_value_paths to flow_ui_share_grants."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260805_0032"
down_revision: Union[str, None] = "20260804_0031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("flow_ui_share_grants")}
    if "redacted_value_paths" in columns:
        return
    op.add_column(
        "flow_ui_share_grants",
        sa.Column(
            "redacted_value_paths",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.alter_column("flow_ui_share_grants", "redacted_value_paths", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("flow_ui_share_grants")}
    if "redacted_value_paths" not in columns:
        return
    op.drop_column("flow_ui_share_grants", "redacted_value_paths")
