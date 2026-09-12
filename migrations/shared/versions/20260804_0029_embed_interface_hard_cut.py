"""Embed interface hard cut.

The chat_override conversion that used to live here is superseded by shared_0033,
which converts every persisted embed config straight to conversation settings;
this revision keeps its place in the chain without touching data.

Revision ID: shared_0029
Revises: shared_0028
Create Date: 2026-08-04
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "shared_0029"
down_revision: str | None = "shared_0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
