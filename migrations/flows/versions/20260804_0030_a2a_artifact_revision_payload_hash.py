"""Add artifact revision and payload_hash to A2A projections."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260804_0030"
down_revision: Union[str, None] = "20260804_0029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "a2a_artifact_projections",
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "a2a_artifact_projections",
        sa.Column("payload_hash", sa.String(), nullable=False, server_default=""),
    )
    op.alter_column("a2a_artifact_projections", "revision", server_default=None)
    op.alter_column("a2a_artifact_projections", "payload_hash", server_default=None)


def downgrade() -> None:
    op.drop_column("a2a_artifact_projections", "payload_hash")
    op.drop_column("a2a_artifact_projections", "revision")
