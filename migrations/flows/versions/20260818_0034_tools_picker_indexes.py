"""Picker indexes for company tools prefix + non-MCP code tab.

Revision ID: 20260818_0034
Revises: 20260811_0033
Create Date: 2026-08-18
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20260818_0034"
down_revision: Union[str, None] = "20260811_0033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tools_key_updated_at "
        "ON tools (key text_pattern_ops, updated_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tools_non_mcp_key_updated_at "
        "ON tools (key text_pattern_ops, updated_at DESC) "
        "WHERE COALESCE(value->>'code_mode', '') IS DISTINCT FROM 'mcp_tool'"
    )


def downgrade() -> None:
    raise NotImplementedError(
        "20260818_0034 downgrade is not supported; reset DB and upgrade head"
    )
