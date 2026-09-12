"""Flow interface hard cut.

The A2UI interface conversion that used to live here is superseded by
20260910_0035, which converts every persisted FlowConfig straight to the block
document grammar; this revision keeps its place in the chain without touching data.

Revision ID: 20260804_0029
Revises: 20260804_0028
Create Date: 2026-08-04
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "20260804_0029"
down_revision: str | None = "20260804_0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
