"""drop access_grants — ACL только OpenFGA

Revision ID: 20260811_0027
Revises: 20260704_0026
Create Date: 2026-08-11
"""

from typing import Sequence, Union

from alembic import op

revision: str = "20260811_0027"
down_revision: Union[str, None] = "20260704_0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS access_grants CASCADE")


def downgrade() -> None:
    raise NotImplementedError(
        "access_grants removed: grants live in OpenFGA only; restore from backup if needed"
    )
