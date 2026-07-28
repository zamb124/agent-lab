"""
Доменные модели wiki.

Верхнеуровневая сущность — платформенный `namespace`: страницы живут внутри
`(company_id, namespace)` и образуют дерево через `parent_page_id`. Страница
с `parent_page_id = None` играет роль раздела верхнего уровня; отдельной
сущности «коллекция» нет.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from apps.wiki.base_model import WikiBaseModel
from apps.wiki.content.prosemirror import ProseMirrorNode


class WikiVisibility(StrEnum):
    """Эффективная видимость страницы.

    Не пользовательская настройка, а материализованный результат ACL: она
    определяет, в какой RAG-namespace попадает контент. Пересчитывается только
    в `WikiAccessService` и переносится в индекс `WikiRagIndexService`.
    """

    COMPANY = "company"
    RESTRICTED = "restricted"


class WikiPagePermission(StrEnum):
    """Уровень доступа участника к странице."""

    READ = "read"
    WRITE = "write"
    ADMIN = "admin"


class WikiLinkPermission(StrEnum):
    """Что позволяет публичная ссылка."""

    VIEW = "view"
    COMMENT = "comment"


class WikiLinkTargetKind(StrEnum):
    """Куда указывает исходящая ссылка страницы."""

    WIKI_PAGE = "wiki_page"
    CRM_ENTITY = "crm_entity"
    FILE = "file"
    WORK_ITEM = "work_item"
    SYNC_MESSAGE = "sync_message"
    URL = "url"


class WikiPageMember(WikiBaseModel):
    """Явный участник страницы.

    Наличие хотя бы одной записи на странице или её предке делает всё
    поддерево `restricted`.
    """

    wiki_page_id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    permission: WikiPagePermission = WikiPagePermission.READ
    created_at: datetime


class WikiPageLink(WikiBaseModel):
    """Исходящая ссылка страницы — основа backlinks во все стороны платформы."""

    wiki_page_link_id: str = Field(..., min_length=1)
    company_id: str = Field(..., min_length=1)
    namespace: str = Field(..., min_length=1)
    source_page_id: str = Field(..., min_length=1)
    target_kind: WikiLinkTargetKind
    target_id: str = Field(..., min_length=1)
    target_label: str = ""
    created_at: datetime


class WikiPage(WikiBaseModel):
    """Страница wiki.

    `content` — источник правды. `text_markdown` производный: его пишет только
    `WikiService` через сериализатор, снаружи он доступен на чтение.
    `root_page_id` и `depth` денормализованы ради дешёвых запросов по разделу
    и фильтров RAG; пересчитываются при перемещении.
    """

    wiki_page_id: str = Field(..., min_length=1)
    company_id: str = Field(..., min_length=1)
    namespace: str = Field(..., min_length=1)
    parent_page_id: str | None = None
    root_page_id: str = Field(..., min_length=1)
    depth: int = Field(default=0, ge=0)
    position: int = 0
    title: str = ""
    icon: str = ""
    cover_url: str = ""
    content: ProseMirrorNode
    text_markdown: str = ""
    visibility: WikiVisibility = WikiVisibility.COMPANY
    is_published: bool = True
    published_at: datetime | None = None
    is_template: bool = False
    is_full_width: bool = False
    link_enabled: bool = False
    link_permission: WikiLinkPermission = WikiLinkPermission.VIEW
    created_by_user_id: str = Field(..., min_length=1)
    last_edited_by_user_id: str = Field(..., min_length=1)
    revision_count: int = Field(default=0, ge=0)
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


class WikiPageSummary(WikiBaseModel):
    """Узел дерева и строка списка — без содержимого страницы.

    Дерево namespace может быть большим, поэтому контент в него не попадает
    ни при каких обстоятельствах.
    """

    wiki_page_id: str = Field(..., min_length=1)
    namespace: str = Field(..., min_length=1)
    parent_page_id: str | None = None
    root_page_id: str = Field(..., min_length=1)
    depth: int = Field(default=0, ge=0)
    position: int = 0
    title: str = ""
    icon: str = ""
    visibility: WikiVisibility = WikiVisibility.COMPANY
    is_published: bool = True
    is_template: bool = False
    has_children: bool = False
    updated_at: datetime
    last_edited_by_user_id: str = Field(..., min_length=1)


class WikiRevision(WikiBaseModel):
    """Снимок страницы на момент сохранения."""

    wiki_revision_id: str = Field(..., min_length=1)
    wiki_page_id: str = Field(..., min_length=1)
    company_id: str = Field(..., min_length=1)
    namespace: str = Field(..., min_length=1)
    title: str = ""
    content: ProseMirrorNode
    text_markdown: str = ""
    author_user_id: str = Field(..., min_length=1)
    created_at: datetime


class WikiRevisionSummary(WikiBaseModel):
    """Строка истории версий без содержимого."""

    wiki_revision_id: str = Field(..., min_length=1)
    wiki_page_id: str = Field(..., min_length=1)
    title: str = ""
    author_user_id: str = Field(..., min_length=1)
    created_at: datetime


class WikiComment(WikiBaseModel):
    """Комментарий к странице.

    `anchor_text` хранит процитированный фрагмент: позиции ProseMirror
    смещаются при правках, поэтому текст — единственный надёжный якорь до
    появления CRDT-относительных позиций.
    """

    wiki_comment_id: str = Field(..., min_length=1)
    wiki_page_id: str = Field(..., min_length=1)
    company_id: str = Field(..., min_length=1)
    namespace: str = Field(..., min_length=1)
    parent_comment_id: str | None = None
    author_user_id: str = Field(..., min_length=1)
    body_markdown: str = ""
    anchor_text: str = ""
    resolved_at: datetime | None = None
    resolved_by_user_id: str | None = None
    created_at: datetime
    updated_at: datetime


class WikiPageAccess(WikiBaseModel):
    """Полная картина доступа к странице для UI настроек."""

    wiki_page_id: str = Field(..., min_length=1)
    visibility: WikiVisibility
    inherited_from_page_id: str | None = None
    members: list[WikiPageMember] = Field(default_factory=list)
    link_enabled: bool = False
    link_permission: WikiLinkPermission = WikiLinkPermission.VIEW
    link_url: str | None = None


class WikiSearchHit(WikiBaseModel):
    """Результат поиска — общий для лексического и семантического слоёв."""

    wiki_page_id: str = Field(..., min_length=1)
    namespace: str = Field(..., min_length=1)
    title: str = ""
    icon: str = ""
    snippet: str = ""
    heading_path: str = ""
    score: float = 0.0
    updated_at: datetime


class WikiBacklink(WikiBaseModel):
    """Обратная ссылка: какая страница ссылается на цель."""

    wiki_page_id: str = Field(..., min_length=1)
    namespace: str = Field(..., min_length=1)
    title: str = ""
    icon: str = ""
    target_kind: WikiLinkTargetKind
    target_id: str = Field(..., min_length=1)
    updated_at: datetime


__all__ = [
    "WikiBacklink",
    "WikiComment",
    "WikiLinkPermission",
    "WikiLinkTargetKind",
    "WikiPage",
    "WikiPageAccess",
    "WikiPageLink",
    "WikiPageMember",
    "WikiPagePermission",
    "WikiPageSummary",
    "WikiRevision",
    "WikiRevisionSummary",
    "WikiSearchHit",
    "WikiVisibility",
]
