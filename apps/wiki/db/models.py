"""
SQLAlchemy модели БД `platform_wiki`.

Изоляция — жёсткая: каждая таблица несёт `company_id` + `namespace`, и любой
поисковый индекс начинается именно с этой пары. Запрос без обоих полей в
`WHERE` считается ошибкой, поэтому индексов «просто по id» здесь нет.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import override

from sqlalchemy import (
    Boolean,
    Computed,
    DateTime,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from core.db.models import Base
from core.types import JsonObject

SEARCH_VECTOR_EXPRESSION: str = (
    "setweight(to_tsvector('simple', coalesce(title, '')), 'A') || "
    "setweight(to_tsvector('simple', coalesce(text_markdown, '')), 'B')"
)
"""Выражение полнотекстового вектора.

Конфигурация `simple` совпадает с CRM: без стемминга поиск одинаково
предсказуем на русском и английском, а платформа двуязычна.
"""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class WikiPageRow(Base):
    __tablename__: str = "wiki_pages"

    wiki_page_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(100), nullable=False)
    namespace: Mapped[str] = mapped_column(String(100), nullable=False)
    parent_page_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    root_page_id: Mapped[str] = mapped_column(String(64), nullable=False)
    depth: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    icon: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    cover_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    content: Mapped[JsonObject] = mapped_column(JSONB, nullable=False)
    text_markdown: Mapped[str] = mapped_column(Text, nullable=False, default="")
    crdt_state: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    company_visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_template: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_full_width: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    link_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    link_token_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    link_permission: Mapped[str] = mapped_column(String(16), nullable=False, default="viewer")
    created_by_user_id: Mapped[str] = mapped_column(String(100), nullable=False)
    last_edited_by_user_id: Mapped[str] = mapped_column(String(100), nullable=False)
    revision_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    search_vector: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed(SEARCH_VECTOR_EXPRESSION, persisted=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__: tuple[object, ...] = (
        Index(
            "ix_wiki_pages_tree",
            "company_id",
            "namespace",
            "parent_page_id",
            "position",
        ),
        Index("ix_wiki_pages_root", "company_id", "namespace", "root_page_id"),
        Index("ix_wiki_pages_updated", "company_id", "namespace", "updated_at"),
        Index("ix_wiki_pages_link_token", "link_token_hash"),
        Index("ix_wiki_pages_search_vector", "search_vector", postgresql_using="gin"),
    )

    @override
    def __repr__(self) -> str:
        return f"<WikiPageRow(wiki_page_id='{self.wiki_page_id}', title='{self.title}')>"


class WikiRevisionRow(Base):
    __tablename__: str = "wiki_revisions"

    wiki_revision_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    wiki_page_id: Mapped[str] = mapped_column(String(64), nullable=False)
    company_id: Mapped[str] = mapped_column(String(100), nullable=False)
    namespace: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    content: Mapped[JsonObject] = mapped_column(JSONB, nullable=False)
    text_markdown: Mapped[str] = mapped_column(Text, nullable=False, default="")
    author_user_id: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__: tuple[object, ...] = (
        Index("ix_wiki_revisions_page", "company_id", "namespace", "wiki_page_id", "created_at"),
    )


class WikiPageLinkRow(Base):
    __tablename__: str = "wiki_page_links"

    wiki_page_link_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(100), nullable=False)
    namespace: Mapped[str] = mapped_column(String(100), nullable=False)
    source_page_id: Mapped[str] = mapped_column(String(64), nullable=False)
    target_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(255), nullable=False)
    target_label: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__: tuple[object, ...] = (
        UniqueConstraint(
            "source_page_id",
            "target_kind",
            "target_id",
            name="uq_wiki_page_links_edge",
        ),
        Index("ix_wiki_page_links_source", "company_id", "namespace", "source_page_id"),
        Index("ix_wiki_page_links_target", "company_id", "target_kind", "target_id"),
    )


class WikiCommentRow(Base):
    __tablename__: str = "wiki_comments"

    wiki_comment_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    wiki_page_id: Mapped[str] = mapped_column(String(64), nullable=False)
    company_id: Mapped[str] = mapped_column(String(100), nullable=False)
    namespace: Mapped[str] = mapped_column(String(100), nullable=False)
    parent_comment_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    author_user_id: Mapped[str] = mapped_column(String(100), nullable=False)
    body_markdown: Mapped[str] = mapped_column(Text, nullable=False, default="")
    anchor_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by_user_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    __table_args__: tuple[object, ...] = (
        Index("ix_wiki_comments_page", "company_id", "namespace", "wiki_page_id", "created_at"),
    )
