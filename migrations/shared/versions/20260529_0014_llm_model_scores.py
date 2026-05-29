"""Платформенный скоринг LLM-моделей.

Revision ID: shared_0014
Revises: shared_0013
Create Date: 2026-05-29
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "shared_0014"
down_revision: Union[str, None] = "shared_0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "llm_model_scores",
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model_id", sa.String(length=512), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column(
            "score_dimensions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("updated_by_user_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "score >= 0 AND score <= 1000",
            name="llm_model_scores_score_range_check",
        ),
        sa.CheckConstraint(
            "source IN ('config_seed','manual','benchmark_import')",
            name="llm_model_scores_source_check",
        ),
        sa.PrimaryKeyConstraint("provider", "model_id"),
    )
    op.create_index("ix_llm_model_scores_provider", "llm_model_scores", ["provider"])
    op.create_index(
        "ix_llm_model_scores_enabled_score",
        "llm_model_scores",
        ["enabled", "score"],
    )
    op.create_index("ix_llm_model_scores_updated_at", "llm_model_scores", ["updated_at"])


def downgrade() -> None:
    op.drop_index("ix_llm_model_scores_updated_at", table_name="llm_model_scores")
    op.drop_index("ix_llm_model_scores_enabled_score", table_name="llm_model_scores")
    op.drop_index("ix_llm_model_scores_provider", table_name="llm_model_scores")
    op.drop_table("llm_model_scores")
