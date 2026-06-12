"""seed runet platform index and crawl profile

Revision ID: search_0002
Revises: search_0001
Create Date: 2026-06-12
"""

from typing import Sequence, Union

from alembic import op

revision: str = "search_0002"
down_revision: Union[str, None] = "search_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO search_indexes (
            search_index_id, company_id, display_name, description,
            rag_namespace_id, rag_collection_id, enabled, search_enabled,
            retrieval_semantic, retrieval_lexical, retrieval_rerank, retrieval_rrf_k,
            snippet_max_chars, indexing_profile_key, created_at, updated_at
        ) VALUES (
            'runet', 'system', 'Runet Web', 'Платформенный индекс русскоязычного веба',
            'runet:platform', 'runet', true, true,
            true, true, true, 60,
            2000, 'runet_web', NOW(), NOW()
        )
        ON CONFLICT (search_index_id) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO crawl_profiles (
            crawl_profile_id, search_index_id, enabled, seed_source,
            refresh_interval_seconds, max_urls_per_domain_per_tick, max_domains_per_tick,
            max_urls_per_batch, http_concurrency, browser_fallback_enabled,
            sitemap_stale_after_seconds, denylist_domains, created_at, updated_at
        ) VALUES (
            'runet_platform', 'runet', true, 'tranco',
            21600, 200, 20, 50, 8, true,
            86400, '[]'::jsonb, NOW(), NOW()
        )
        ON CONFLICT (crawl_profile_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM crawl_profiles WHERE crawl_profile_id = 'runet_platform'")
    op.execute("DELETE FROM search_indexes WHERE search_index_id = 'runet'")
