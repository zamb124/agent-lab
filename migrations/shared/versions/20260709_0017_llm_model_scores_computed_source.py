"""Allow computed source for LLM model scoring.

Revision ID: shared_0017
Revises: shared_0016
Create Date: 2026-07-09
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

from alembic import op

revision: str = "shared_0017"
down_revision: Union[str, None] = "shared_0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("llm_model_scores_source_check", "llm_model_scores", type_="check")
    op.create_check_constraint(
        "llm_model_scores_source_check",
        "llm_model_scores",
        "source IN ('config_seed','manual','benchmark_import','computed')",
    )


def downgrade() -> None:
    op.drop_constraint("llm_model_scores_source_check", "llm_model_scores", type_="check")
    op.create_check_constraint(
        "llm_model_scores_source_check",
        "llm_model_scores",
        "source IN ('config_seed','manual','benchmark_import')",
    )
