"""extractable and is_voice_target on entity_types and namespace_template_types

Revision ID: crm_0014
Revises: crm_0013
Create Date: 2026-04-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "crm_0014"
down_revision: Union[str, None] = "crm_0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "entity_types",
        sa.Column(
            "extractable",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "entity_types",
        sa.Column(
            "is_voice_target",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "namespace_template_types",
        sa.Column(
            "is_voice_target",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("namespace_template_types", "is_voice_target")
    op.drop_column("entity_types", "is_voice_target")
    op.drop_column("entity_types", "extractable")
