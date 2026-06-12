"""search_indexes and crawl tables

Revision ID: search_0001
Revises:
Create Date: 2026-06-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "search_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "search_indexes",
        sa.Column("search_index_id", sa.String(length=64), nullable=False),
        sa.Column("company_id", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=512), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("rag_namespace_id", sa.String(length=255), nullable=False),
        sa.Column("rag_collection_id", sa.String(length=128), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("search_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("retrieval_semantic", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("retrieval_lexical", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("retrieval_rerank", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("retrieval_rrf_k", sa.Integer(), nullable=True),
        sa.Column("retrieval_per_channel_top_k", sa.Integer(), nullable=True),
        sa.Column("snippet_max_chars", sa.Integer(), nullable=False, server_default=sa.text("2000")),
        sa.Column("indexing_profile_key", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("search_index_id"),
        sa.UniqueConstraint("company_id", "rag_namespace_id", name="uq_search_indexes_company_namespace"),
        sa.UniqueConstraint("company_id", "rag_collection_id", name="uq_search_indexes_company_collection"),
    )
    op.create_index("ix_search_indexes_company_enabled", "search_indexes", ["company_id", "enabled"])

    op.create_table(
        "crawl_profiles",
        sa.Column("crawl_profile_id", sa.String(length=64), nullable=False),
        sa.Column("search_index_id", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("seed_source", sa.String(length=32), nullable=False),
        sa.Column("refresh_interval_seconds", sa.Integer(), nullable=False, server_default=sa.text("21600")),
        sa.Column("max_urls_per_domain_per_tick", sa.Integer(), nullable=False, server_default=sa.text("200")),
        sa.Column("max_domains_per_tick", sa.Integer(), nullable=False, server_default=sa.text("20")),
        sa.Column("max_urls_per_batch", sa.Integer(), nullable=False, server_default=sa.text("50")),
        sa.Column("http_concurrency", sa.Integer(), nullable=False, server_default=sa.text("8")),
        sa.Column("browser_fallback_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sitemap_stale_after_seconds", sa.Integer(), nullable=False, server_default=sa.text("86400")),
        sa.Column("denylist_domains", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["search_index_id"], ["search_indexes.search_index_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("crawl_profile_id"),
    )
    op.create_index("ix_crawl_profiles_search_index_id", "crawl_profiles", ["search_index_id"])

    op.create_table(
        "crawl_domains",
        sa.Column("crawl_domain_id", sa.String(length=36), nullable=False),
        sa.Column("crawl_profile_id", sa.String(length=64), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("domain_rank", sa.Integer(), nullable=True),
        sa.Column("category", sa.String(length=32), nullable=False, server_default=sa.text("'unknown'")),
        sa.Column("crawl_policy", sa.String(length=32), nullable=False, server_default=sa.text("'sitemap_only'")),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'active'")),
        sa.Column("last_discovered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_crawled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_crawl_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["crawl_profile_id"], ["crawl_profiles.crawl_profile_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("crawl_domain_id"),
        sa.UniqueConstraint("crawl_profile_id", "domain", name="uq_crawl_domains_profile_domain"),
    )
    op.create_index("ix_crawl_domains_due", "crawl_domains", ["crawl_profile_id", "next_crawl_after"])

    op.create_table(
        "crawl_urls",
        sa.Column("crawl_url_id", sa.String(length=36), nullable=False),
        sa.Column("crawl_domain_id", sa.String(length=36), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("sitemap_lastmod", sa.DateTime(timezone=True), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("crawl_status", sa.String(length=32), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("document_id", sa.String(length=255), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_crawled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["crawl_domain_id"], ["crawl_domains.crawl_domain_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("crawl_url_id"),
        sa.UniqueConstraint("crawl_domain_id", "canonical_url", name="uq_crawl_urls_domain_canonical"),
    )
    op.create_index("ix_crawl_urls_domain_status", "crawl_urls", ["crawl_domain_id", "crawl_status"])

    op.create_table(
        "crawl_jobs",
        sa.Column("crawl_job_id", sa.String(length=36), nullable=False),
        sa.Column("crawl_profile_id", sa.String(length=64), nullable=False),
        sa.Column("trigger", sa.String(length=32), nullable=False),
        sa.Column("schedule_task_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'running'")),
        sa.Column("domains_scheduled", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("urls_discovered", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("urls_fetched", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("urls_indexed", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("urls_skipped", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("errors", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["crawl_profile_id"], ["crawl_profiles.crawl_profile_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("crawl_job_id"),
    )
    op.create_index("ix_crawl_jobs_profile_id", "crawl_jobs", ["crawl_profile_id"])

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
        """
    )


def downgrade() -> None:
    op.drop_index("ix_crawl_jobs_profile_id", table_name="crawl_jobs")
    op.drop_table("crawl_jobs")
    op.drop_index("ix_crawl_urls_domain_status", table_name="crawl_urls")
    op.drop_table("crawl_urls")
    op.drop_index("ix_crawl_domains_due", table_name="crawl_domains")
    op.drop_table("crawl_domains")
    op.drop_index("ix_crawl_profiles_search_index_id", table_name="crawl_profiles")
    op.drop_table("crawl_profiles")
    op.drop_index("ix_search_indexes_company_enabled", table_name="search_indexes")
    op.drop_table("search_indexes")
