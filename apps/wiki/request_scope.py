"""Граница страницы wiki: can_view / can_edit / can_admin из OpenFGA.

Компания, пользователь и пространство — `core.request_scope.require_namespace`.
Проверка `platform_namespace` viewer — в `op_*` (`_scope`), не здесь.
"""

from __future__ import annotations

from apps.wiki.container import WikiContainer
from apps.wiki.models.api import WikiPageResponse
from apps.wiki.models.domain import WikiPage
from core.authz.models import AuthzObject
from core.request_scope import NamespaceScope


async def load_viewable_page(
    container: WikiContainer, scope: NamespaceScope, wiki_page_id: str
) -> WikiPage:
    """Страница, доступная пользователю на чтение.

    Отсутствие страницы и чужое пространство дают одинаковый not_found:
    разные ответы раскрывали бы существование страницы за пределами доступа.
    """
    return await container.wiki_service.require_viewable_page(
        scope.company_id, scope.namespace, wiki_page_id, scope.user_id
    )


async def wiki_page_response(
    container: WikiContainer, page: WikiPage, *, user_id: str
) -> WikiPageResponse:
    """can_edit / can_admin только из AuthzService (включая mutating-ответы)."""
    obj = AuthzObject.wiki_page(page.wiki_page_id)
    can_edit = await container.authz_service.can_edit(obj, user_id=user_id)
    can_admin = await container.authz_service.can_admin(obj, user_id=user_id)
    return WikiPageResponse(page=page, can_edit=can_edit, can_admin=can_admin)


__all__ = [
    "load_viewable_page",
    "wiki_page_response",
]
