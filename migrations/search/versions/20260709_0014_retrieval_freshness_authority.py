"""retrieval freshness, domain authority and capped rerank

Revision ID: search_0014
Revises: search_0013
Create Date: 2026-07-09
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "search_0014"
down_revision: Union[str, None] = "search_0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "search_indexes",
        sa.Column("retrieval_rerank_max_candidates", sa.Integer(), nullable=True),
    )
    op.add_column(
        "search_indexes",
        sa.Column(
            "retrieval_freshness_weight",
            sa.Float(),
            nullable=False,
            server_default="0.0",
        ),
    )
    op.add_column(
        "search_indexes",
        sa.Column(
            "retrieval_freshness_half_life_days",
            sa.Float(),
            nullable=False,
            server_default="180.0",
        ),
    )
    op.add_column(
        "search_indexes",
        sa.Column(
            "retrieval_freshness_recency_half_life_days",
            sa.Float(),
            nullable=False,
            server_default="30.0",
        ),
    )
    op.add_column(
        "search_indexes",
        sa.Column(
            "retrieval_domain_authority_weight",
            sa.Float(),
            nullable=False,
            server_default="0.0",
        ),
    )
    # Runet: rerank возвращается с жёстким капом top-30 (GPU-нагрузка ~ пул rerank,
    # а не per_channel_top_k — Postgres-каналы снова 120), плюс freshness и
    # мягкий Tranco-приор.
    op.execute(
        """
        UPDATE search_indexes
        SET retrieval_rerank = true,
            retrieval_rerank_max_candidates = 30,
            retrieval_per_channel_top_k = 120,
            retrieval_freshness_weight = 0.5,
            retrieval_freshness_half_life_days = 180.0,
            retrieval_freshness_recency_half_life_days = 30.0,
            retrieval_domain_authority_weight = 0.1,
            updated_at = NOW()
        WHERE search_index_id = 'runet'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE search_indexes
        SET retrieval_rerank = false,
            retrieval_per_channel_top_k = 50,
            updated_at = NOW()
        WHERE search_index_id = 'runet'
        """
    )
    op.drop_column("search_indexes", "retrieval_domain_authority_weight")
    op.drop_column("search_indexes", "retrieval_freshness_recency_half_life_days")
    op.drop_column("search_indexes", "retrieval_freshness_half_life_days")
    op.drop_column("search_indexes", "retrieval_freshness_weight")
    op.drop_column("search_indexes", "retrieval_rerank_max_candidates")
