"""LLM model scores store only manual overlays.

Revision ID: shared_0034
Revises: shared_0033
Create Date: 2026-09-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "shared_0034"
down_revision: str | None = "shared_0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "llm_model_scores",
        sa.Column(
            "editorial_prior",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
    )
    op.execute(
        """
        UPDATE llm_model_scores
        SET editorial_prior = GREATEST(
            -5.0,
            LEAST(
                5.0,
                COALESCE((score_dimensions->>'$editorial_prior')::double precision, 0)
            )
        )
        """
    )
    op.drop_index("ix_llm_model_scores_enabled_score", table_name="llm_model_scores")
    op.drop_constraint("llm_model_scores_score_range_check", "llm_model_scores", type_="check")
    op.drop_constraint("llm_model_scores_source_check", "llm_model_scores", type_="check")
    op.drop_column("llm_model_scores", "score")
    op.drop_column("llm_model_scores", "source")
    op.drop_column("llm_model_scores", "score_dimensions")
    op.create_index("ix_llm_model_scores_enabled", "llm_model_scores", ["enabled"])
    op.create_check_constraint(
        "llm_model_scores_editorial_prior_range_check",
        "llm_model_scores",
        "editorial_prior >= -5 AND editorial_prior <= 5",
    )


def downgrade() -> None:
    op.drop_constraint(
        "llm_model_scores_editorial_prior_range_check",
        "llm_model_scores",
        type_="check",
    )
    op.drop_index("ix_llm_model_scores_enabled", table_name="llm_model_scores")
    op.add_column(
        "llm_model_scores",
        sa.Column("score", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "llm_model_scores",
        sa.Column("source", sa.String(length=32), nullable=False, server_default="manual"),
    )
    op.add_column(
        "llm_model_scores",
        sa.Column(
            "score_dimensions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.execute(
        """
        UPDATE llm_model_scores
        SET score_dimensions = jsonb_build_object('$editorial_prior', editorial_prior)
        WHERE editorial_prior <> 0
        """
    )
    op.create_check_constraint(
        "llm_model_scores_score_range_check",
        "llm_model_scores",
        "score >= 0 AND score <= 1000",
    )
    op.create_check_constraint(
        "llm_model_scores_source_check",
        "llm_model_scores",
        "source IN ('config_seed','manual','benchmark_import','computed')",
    )
    op.create_index(
        "ix_llm_model_scores_enabled_score",
        "llm_model_scores",
        ["enabled", "score"],
    )
    op.drop_column("llm_model_scores", "editorial_prior")
