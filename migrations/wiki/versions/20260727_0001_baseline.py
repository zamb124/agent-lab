"""Базовая миграция БД platform_wiki (база знаний)

Revision ID: wiki_0001
Revises:
Create Date: 2026-07-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

_SEARCH_VECTOR_EXPRESSION = (
    "setweight(to_tsvector('simple', coalesce(title, '')), 'A') || "
    "setweight(to_tsvector('simple', coalesce(text_markdown, '')), 'B')"
)

revision: str = "wiki_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "wiki_pages",
        sa.Column("wiki_page_id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("company_id", sa.String(100), nullable=False),
        sa.Column("namespace", sa.String(100), nullable=False),
        sa.Column("parent_page_id", sa.String(64), nullable=True),
        sa.Column("root_page_id", sa.String(64), nullable=False),
        sa.Column("depth", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("title", sa.Text(), nullable=False, server_default=""),
        sa.Column("icon", sa.String(64), nullable=False, server_default=""),
        sa.Column("cover_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("content", postgresql.JSONB(), nullable=False),
        sa.Column("text_markdown", sa.Text(), nullable=False, server_default=""),
        sa.Column("crdt_state", sa.LargeBinary(), nullable=True),
        sa.Column("visibility", sa.String(16), nullable=False, server_default="company"),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_template", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("link_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("link_token_hash", sa.String(128), nullable=True),
        sa.Column("link_permission", sa.String(16), nullable=False, server_default="view"),
        sa.Column("created_by_user_id", sa.String(100), nullable=False),
        sa.Column("last_edited_by_user_id", sa.String(100), nullable=False),
        sa.Column("revision_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(_SEARCH_VECTOR_EXPRESSION, persisted=True),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_wiki_pages_tree",
        "wiki_pages",
        ["company_id", "namespace", "parent_page_id", "position"],
    )
    op.create_index(
        "ix_wiki_pages_root", "wiki_pages", ["company_id", "namespace", "root_page_id"]
    )
    op.create_index(
        "ix_wiki_pages_updated", "wiki_pages", ["company_id", "namespace", "updated_at"]
    )
    op.create_index("ix_wiki_pages_link_token", "wiki_pages", ["link_token_hash"])
    op.create_index(
        "ix_wiki_pages_search_vector",
        "wiki_pages",
        ["search_vector"],
        postgresql_using="gin",
    )

    op.create_table(
        "wiki_revisions",
        sa.Column("wiki_revision_id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("wiki_page_id", sa.String(64), nullable=False),
        sa.Column("company_id", sa.String(100), nullable=False),
        sa.Column("namespace", sa.String(100), nullable=False),
        sa.Column("title", sa.Text(), nullable=False, server_default=""),
        sa.Column("content", postgresql.JSONB(), nullable=False),
        sa.Column("text_markdown", sa.Text(), nullable=False, server_default=""),
        sa.Column("author_user_id", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_wiki_revisions_page",
        "wiki_revisions",
        ["company_id", "namespace", "wiki_page_id", "created_at"],
    )

    op.create_table(
        "wiki_page_members",
        sa.Column("wiki_page_id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("user_id", sa.String(100), primary_key=True, nullable=False),
        sa.Column("company_id", sa.String(100), nullable=False),
        sa.Column("namespace", sa.String(100), nullable=False),
        sa.Column("permission", sa.String(16), nullable=False, server_default="read"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_wiki_page_members_scope",
        "wiki_page_members",
        ["company_id", "namespace", "wiki_page_id"],
    )
    op.create_index(
        "ix_wiki_page_members_user", "wiki_page_members", ["company_id", "user_id"]
    )

    op.create_table(
        "wiki_page_links",
        sa.Column("wiki_page_link_id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("company_id", sa.String(100), nullable=False),
        sa.Column("namespace", sa.String(100), nullable=False),
        sa.Column("source_page_id", sa.String(64), nullable=False),
        sa.Column("target_kind", sa.String(32), nullable=False),
        sa.Column("target_id", sa.String(255), nullable=False),
        sa.Column("target_label", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "source_page_id", "target_kind", "target_id", name="uq_wiki_page_links_edge"
        ),
    )
    op.create_index(
        "ix_wiki_page_links_source",
        "wiki_page_links",
        ["company_id", "namespace", "source_page_id"],
    )
    op.create_index(
        "ix_wiki_page_links_target",
        "wiki_page_links",
        ["company_id", "target_kind", "target_id"],
    )

    op.create_table(
        "wiki_comments",
        sa.Column("wiki_comment_id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("wiki_page_id", sa.String(64), nullable=False),
        sa.Column("company_id", sa.String(100), nullable=False),
        sa.Column("namespace", sa.String(100), nullable=False),
        sa.Column("parent_comment_id", sa.String(64), nullable=True),
        sa.Column("author_user_id", sa.String(100), nullable=False),
        sa.Column("body_markdown", sa.Text(), nullable=False, server_default=""),
        sa.Column("anchor_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by_user_id", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_wiki_comments_page",
        "wiki_comments",
        ["company_id", "namespace", "wiki_page_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("wiki_comments")
    op.drop_table("wiki_page_links")
    op.drop_table("wiki_page_members")
    op.drop_table("wiki_revisions")
    op.drop_table("wiki_pages")
