"""No-op placeholder after durable workflow ledger cutover.

Revision ID: agents_0008
Revises: agents_0007
Create Date: 2026-05-23
"""

from typing import Sequence, Union

revision: str = "agents_0008"
down_revision: Union[str, None] = "agents_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
