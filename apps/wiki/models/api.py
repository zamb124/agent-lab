"""
Контракты HTTP API wiki.

Отдельные модели запроса и ответа нужны потому, что их форма действительно
другая: клиент не присылает вычисляемые поля (`root_page_id`, `depth`,
`company_visible`, `text_markdown`) — они выводятся сервисом.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from apps.wiki.base_model import WikiBaseModel
from apps.wiki.content.markdown_notices import WikiMarkdownNotice
from apps.wiki.content.prosemirror import ProseMirrorNode
from apps.wiki.models.domain import (
    WikiAccessMemberRelation,
    WikiLinkPermission,
    WikiPage,
    WikiPageSummary,
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
    is_full_width: bool | None = None


class WikiPageMoveRequest(WikiBaseModel):
    parent_page_id: str | None = None
    position: int | None = Field(default=None, ge=0)


class WikiPageMoveNamespaceRequest(WikiBaseModel):
    """Перенос поддерева в другое пространство."""

    target_namespace: str = Field(..., min_length=1)
    parent_page_id: str | None = None


class WikiPageResponse(WikiBaseModel):
    """Страница целиком, вместе с содержимым."""

    page: WikiPage
    can_edit: bool = False
    can_admin: bool = False


class WikiTreeResponse(WikiBaseModel):
    namespace: str
    items: list[WikiPageSummary] = Field(default_factory=list)


class WikiMemberUpsertRequest(WikiBaseModel):
    user_id: str = Field(..., min_length=1)
    relation: WikiAccessMemberRelation = "viewer"


class WikiCompanyVisibleRequest(WikiBaseModel):
    company_visible: bool


class WikiPublicLinkRequest(WikiBaseModel):
    enabled: bool
    permission: WikiLinkPermission = WikiLinkPermission.VIEWER


class WikiPublicLinkResponse(WikiBaseModel):
    """Ответ на выпуск публичной ссылки.

    `url` приходит единственный раз: в базе хранится только хеш токена,
    восстановить его позже нельзя.
    """

    enabled: bool
    permission: WikiLinkPermission
    url: str | None = None


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


class WikiCommentCreateRequest(WikiBaseModel):
    body_markdown: str = Field(..., min_length=1)
    anchor_text: str = ""
    parent_comment_id: str | None = None


class WikiCommentResolveRequest(WikiBaseModel):
    resolved: bool = True


class WikiPublicPageResponse(WikiBaseModel):
    """Страница публичного сайта — без служебных полей и прав."""

    wiki_page_id: str
    parent_page_id: str | None = None
    title: str = ""
    icon: str = ""
    cover_url: str = ""
    is_full_width: bool = False
    content: ProseMirrorNode
    updated_at: datetime


class WikiPublicPageSummary(WikiBaseModel):
    """Узел навигации публичного сайта."""

    wiki_page_id: str
    parent_page_id: str | None = None
    title: str = ""
    icon: str = ""
    has_children: bool = False


class WikiPublicTreeResponse(WikiBaseModel):
    """Состав сайта: корень ссылки и все опубликованные страницы под ним."""

    root_page_id: str
    items: list[WikiPublicPageSummary] = Field(default_factory=list)


class WikiMarkdownResponse(WikiBaseModel):
    """Markdown-представление страницы для экспорта и агентов."""

    wiki_page_id: str
    title: str = ""
    markdown: str = ""


class WikiMarkdownImportRequest(WikiBaseModel):
    """Содержимое markdown-файла для импорта."""

    markdown: str = Field(..., description="Текст файла целиком, включая YAML-шапку")
    parent_page_id: str | None = Field(
        default=None,
        description="Родитель новой страницы; игнорируется при импорте в существующую",
    )
    apply_front_matter: bool = Field(
        default=True,
        description="Брать из YAML-шапки заголовок, иконку и обложку страницы",
    )


class WikiMarkdownParseRequest(WikiBaseModel):
    """Markdown для разбора без записи страницы."""

    markdown: str


class WikiMarkdownParseResponse(WikiBaseModel):
    """Документ из markdown плюс заметки о расхождениях."""

    document: ProseMirrorNode
    notices: list[WikiMarkdownNotice] = Field(default_factory=list)


class WikiMarkdownImportResponse(WikiBaseModel):
    """Страница после импорта плюс то, что не перенеслось из файла."""

    page: WikiPage
    notices: list[WikiMarkdownNotice] = Field(default_factory=list)
