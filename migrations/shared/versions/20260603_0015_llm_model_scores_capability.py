"""Capability-aware AI model scoring.

Revision ID: shared_0015
Revises: shared_0014
Create Date: 2026-06-03
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "shared_0015"
down_revision: Union[str, None] = "shared_0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "llm_model_scores",
        sa.Column(
            "capability",
            sa.String(length=64),
            nullable=False,
            server_default="llm_chat",
        ),
    )
    op.drop_constraint("llm_model_scores_pkey", "llm_model_scores", type_="primary")
    op.create_primary_key(
        "llm_model_scores_pkey",
        "llm_model_scores",
        ["provider", "model_id", "capability"],
    )
    op.create_index("ix_llm_model_scores_capability", "llm_model_scores", ["capability"])
    op.alter_column("llm_model_scores", "capability", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_llm_model_scores_capability", table_name="llm_model_scores")
    op.drop_constraint("llm_model_scores_pkey", "llm_model_scores", type_="primary")
    op.create_primary_key(
        "llm_model_scores_pkey",
        "llm_model_scores",
        ["provider", "model_id"],
    )
    op.drop_column("llm_model_scores", "capability")
