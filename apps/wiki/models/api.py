"""
Контракты HTTP API wiki.

Отдельные модели запроса и ответа нужны потому, что их форма действительно
другая: клиент не присылает вычисляемые поля (`root_page_id`, `depth`,
`visibility`, `text_markdown`) — они выводятся сервисом.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from apps.wiki.base_model import WikiBaseModel
from apps.wiki.content.prosemirror import ProseMirrorNode
from apps.wiki.models.domain import (
    WikiComment,
    WikiLinkPermission,
    WikiPage,
    WikiPageMember,
    WikiPagePermission,
    WikiPageSummary,
    WikiVisibility,
)


class WikiPageCreateRequest(WikiBaseModel):
    title: str = Field("", max_length=500)
    parent_page_id: str | None = None
    icon: str = Field("", max_length=64)
    content: ProseMirrorNode | None = None
    markdown: str | None = Field(
        default=None,
        description="Начальное содержимое в markdown. Взаимоисключимо с content.",
    )


class WikiPageContentUpdateRequest(WikiBaseModel):
    content: ProseMirrorNode | None = None
    markdown: str | None = Field(
        default=None,
        description="Новое содержимое в markdown. Взаимоисключимо с content.",
    )
    title: str | None = Field(default=None, max_length=500)
    create_revision: bool = True


class WikiPagePropertiesUpdateRequest(WikiBaseModel):
    title: str | None = Field(default=None, max_length=500)
    icon: str | None = Field(default=None, max_length=64)
    cover_url: str | None = None
    is_published: bool | None = None
    is_template: bool | None = None


class WikiPageMoveRequest(WikiBaseModel):
    parent_page_id: str | None = None
    position: int | None = Field(default=None, ge=0)


class WikiPageMoveNamespaceRequest(WikiBaseModel):
    """Перенос поддерева в другое пространство.

    Отдельный запрос, а не поле в PATCH: операция меняет границу изоляции
    и всегда затрагивает всё поддерево.
    """

    target_namespace: str = Field(..., min_length=1)
    parent_page_id: str | None = None


class WikiPageResponse(WikiBaseModel):
    """Страница целиком, вместе с содержимым."""

    page: WikiPage
    can_edit: bool = False
    can_administer: bool = False


class WikiTreeResponse(WikiBaseModel):
    namespace: str
    items: list[WikiPageSummary] = Field(default_factory=list)


class WikiMemberUpsertRequest(WikiBaseModel):
    user_id: str = Field(..., min_length=1)
    permission: WikiPagePermission = WikiPagePermission.READ


class WikiPublicLinkRequest(WikiBaseModel):
    enabled: bool
    permission: WikiLinkPermission = WikiLinkPermission.VIEW


class WikiPublicLinkResponse(WikiBaseModel):
    """Ответ на выпуск публичной ссылки.

    `url` приходит единственный раз: в базе хранится только хеш токена,
    восстановить его позже нельзя.
    """

    enabled: bool
    permission: WikiLinkPermission
    url: str | None = None


class WikiAccessResponse(WikiBaseModel):
    wiki_page_id: str
    visibility: WikiVisibility
    inherited_from_page_id: str | None = None
    members: list[WikiPageMember] = Field(default_factory=list)
    link_enabled: bool = False
    link_permission: WikiLinkPermission = WikiLinkPermission.VIEW


class WikiSearchRequest(WikiBaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    mode: str = Field(
        "auto",
        description="auto — сначала смысл, потом текст; lexical — только текст; semantic — только смысл.",
    )
    root_page_id: str | None = None
    published_only: bool = False
    updated_after_days: int | None = Field(default=None, ge=1, le=3650)
    editor_user_id: str | None = None
    limit: int = Field(20, ge=1, le=50)


class WikiSearchResultItem(WikiBaseModel):
    wiki_page_id: str
    namespace: str
    title: str = ""
    icon: str = ""
    snippet: str = ""
    heading_path: str = ""
    score: float = 0.0
    channel: str = "lexical"
    updated_at: datetime


class WikiSearchResponse(WikiBaseModel):
    items: list[WikiSearchResultItem] = Field(default_factory=list)


class WikiCommentCreateRequest(WikiBaseModel):
    body_markdown: str = Field(..., min_length=1)
    anchor_text: str = ""
    parent_comment_id: str | None = None


class WikiCommentResolveRequest(WikiBaseModel):
    resolved: bool = True


class WikiCommentListResponse(WikiBaseModel):
    items: list[WikiComment] = Field(default_factory=list)


class WikiBacklinkItem(WikiBaseModel):
    wiki_page_id: str
    namespace: str
    title: str = ""
    icon: str = ""
    url: str
    updated_at: datetime


class WikiBacklinksResponse(WikiBaseModel):
    items: list[WikiBacklinkItem] = Field(default_factory=list)


class WikiPublicPageResponse(WikiBaseModel):
    """Страница по публичной ссылке — без служебных полей и прав."""

    wiki_page_id: str
    title: str = ""
    icon: str = ""
    content: ProseMirrorNode
    updated_at: datetime


class WikiMarkdownResponse(WikiBaseModel):
    """Markdown-представление страницы для экспорта и агентов."""

    wiki_page_id: str
    title: str = ""
    markdown: str = ""
