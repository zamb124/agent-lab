"""company_voice_providers: JSONB secrets per company/kind.

Revision ID: shared_0010
Revises: shared_0009
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "shared_0010"
down_revision: Union[str, None] = "shared_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "company_voice_providers",
        sa.Column(
            "secrets",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("company_voice_providers", "secrets")
