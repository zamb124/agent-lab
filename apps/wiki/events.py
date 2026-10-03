"""
События wiki на шине `platform:events`.

Доменные факты о страницах публикуются только здесь. Эфемерный трафик
совместного редактирования (курсоры, дельты) на шину не попадает — для него
существует отдельный сокет, и смешивать эти потоки нельзя.
"""

from __future__ import annotations

from pydantic import BaseModel

from apps.wiki.models.comment import WikiComment
from apps.wiki.models.domain import (
    WikiPageSummary,
    WikiVisibility,
)
from core.events import publish_event_to_company, register_platform_event

WIKI_PAGE_CREATED = "wiki/page/created"
WIKI_PAGE_UPDATED = "wiki/page/updated"
WIKI_PAGE_PUBLISHED = "wiki/page/published"
WIKI_PAGE_MOVED = "wiki/page/moved"
WIKI_PAGE_DELETED = "wiki/page/deleted"
WIKI_PAGE_RESTORED = "wiki/page/restored"
WIKI_PAGE_ACCESS_CHANGED = "wiki/page/access_changed"
WIKI_COMMENT_CREATED = "wiki/comment/created"
WIKI_COMMENT_RESOLVED = "wiki/comment/resolved"


class WikiPageEventPayload(BaseModel):
    """Payload событий жизненного цикла страницы.

    Содержимое страницы не передаётся: событие уходит всей компании, а текст
    может быть ограниченным.
    """

    page: WikiPageSummary


class WikiPageMovedEventPayload(BaseModel):
    """Payload `wiki/page/moved` — включая перенос между пространствами."""

    page: WikiPageSummary
    previous_namespace: str
    previous_parent_page_id: str | None = None


class WikiPageDeletedEventPayload(BaseModel):
    """Payload `wiki/page/deleted` — удаляется всегда поддерево целиком."""

    wiki_page_id: str
    namespace: str
    affected_page_ids: list[str]


class WikiPageAccessChangedEventPayload(BaseModel):
    """Payload `wiki/page/access_changed`.

    Несёт итоговую видимость поддерева: по этому событию потребители понимают,
    что страница сменила слой индексации.
    """

    wiki_page_id: str
    namespace: str
    visibility: WikiVisibility
    affected_page_ids: list[str]


class WikiCommentEventPayload(BaseModel):
    """Payload событий комментариев."""

    comment: WikiComment


register_platform_event(
    WIKI_PAGE_CREATED,
    WikiPageEventPayload,
    description="Создана страница wiki.",
)
register_platform_event(
    WIKI_PAGE_UPDATED,
    WikiPageEventPayload,
    description="Изменены содержимое или свойства страницы wiki.",
)
register_platform_event(
    WIKI_PAGE_PUBLISHED,
    WikiPageEventPayload,
    description="Страница wiki опубликована.",
)
register_platform_event(
    WIKI_PAGE_MOVED,
    WikiPageMovedEventPayload,
    description="Страница wiki перемещена в дереве или в другое пространство.",
)
register_platform_event(
    WIKI_PAGE_DELETED,
    WikiPageDeletedEventPayload,
    description="Страница wiki и её поддерево перемещены в корзину.",
)
register_platform_event(
    WIKI_PAGE_RESTORED,
    WikiPageEventPayload,
    description="Страница wiki восстановлена из корзины.",
)
register_platform_event(
    WIKI_PAGE_ACCESS_CHANGED,
    WikiPageAccessChangedEventPayload,
    description="Изменён доступ к странице wiki; поддерево сменило видимость.",
)
register_platform_event(
    WIKI_COMMENT_CREATED,
    WikiCommentEventPayload,
    description="К странице wiki добавлен комментарий.",
)
register_platform_event(
    WIKI_COMMENT_RESOLVED,
    WikiCommentEventPayload,
    description="Комментарий на странице wiki закрыт.",
)


async def publish_wiki_page_event(
    event_type: str, page: WikiPageSummary, company_id: str
) -> None:
    payload = WikiPageEventPayload(page=page)
    await publish_event_to_company(
        company_id=company_id,
        type=event_type,
        payload=payload.model_dump(mode="json"),
    )


async def publish_wiki_page_moved(
    page: WikiPageSummary,
    company_id: str,
    previous_namespace: str,
    previous_parent_page_id: str | None,
) -> None:
    payload = WikiPageMovedEventPayload(
        page=page,
        previous_namespace=previous_namespace,
        previous_parent_page_id=previous_parent_page_id,
    )
    await publish_event_to_company(
        company_id=company_id,
        type=WIKI_PAGE_MOVED,
        payload=payload.model_dump(mode="json"),
    )


async def publish_wiki_page_deleted(
    wiki_page_id: str, namespace: str, company_id: str, affected_page_ids: list[str]
) -> None:
    payload = WikiPageDeletedEventPayload(
        wiki_page_id=wiki_page_id,
        namespace=namespace,
        affected_page_ids=affected_page_ids,
    )
    await publish_event_to_company(
        company_id=company_id,
        type=WIKI_PAGE_DELETED,
        payload=payload.model_dump(mode="json"),
    )


async def publish_wiki_access_changed(
    wiki_page_id: str,
    namespace: str,
    company_id: str,
    visibility: WikiVisibility,
    affected_page_ids: list[str],
) -> None:
    payload = WikiPageAccessChangedEventPayload(
        wiki_page_id=wiki_page_id,
        namespace=namespace,
        visibility=visibility,
        affected_page_ids=affected_page_ids,
    )
    await publish_event_to_company(
        company_id=company_id,
        type=WIKI_PAGE_ACCESS_CHANGED,
        payload=payload.model_dump(mode="json"),
    )


async def publish_wiki_comment_event(
    event_type: str, comment: WikiComment, company_id: str
) -> None:
    payload = WikiCommentEventPayload(comment=comment)
    await publish_event_to_company(
        company_id=company_id,
        type=event_type,
        payload=payload.model_dump(mode="json"),
    )


__all__ = [
    "WIKI_COMMENT_CREATED",
    "WIKI_COMMENT_RESOLVED",
    "WIKI_PAGE_ACCESS_CHANGED",
    "WIKI_PAGE_CREATED",
    "WIKI_PAGE_DELETED",
    "WIKI_PAGE_MOVED",
    "WIKI_PAGE_PUBLISHED",
    "WIKI_PAGE_RESTORED",
    "WIKI_PAGE_UPDATED",
    "WikiCommentEventPayload",
    "WikiPageAccessChangedEventPayload",
    "WikiPageDeletedEventPayload",
    "WikiPageEventPayload",
    "WikiPageMovedEventPayload",
    "publish_wiki_access_changed",
    "publish_wiki_comment_event",
    "publish_wiki_page_deleted",
    "publish_wiki_page_event",
    "publish_wiki_page_moved",
]
