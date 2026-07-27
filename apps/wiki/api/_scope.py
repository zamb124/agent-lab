"""
Границы запроса к wiki: компания, пользователь, пространство.

Namespace обязателен для всех операций и берётся только из платформенного
контекста (`X-Platform-Namespace`), как в Documents и Networkle. Если клиент
не выбрал пространство, контекст платформы подставляет системное `default` —
это существующий workspace компании, а не «отсутствие границы»: данные всё
равно изолированы, просто запрос адресован дефолтному пространству.

Пространство всегда проверяется на существование и принадлежность активной
компании; несуществующее имя — ошибка, а не повод молча уйти в `default`.
"""

from __future__ import annotations

from fastapi import HTTPException

from apps.wiki.container import WikiContainer
from apps.wiki.models.domain import WikiPage
from apps.wiki.services.wiki_service import WikiAccessDeniedError, WikiPageNotFoundError
from core.context import get_context
from core.models.base import StrictBaseModel

ANONYMOUS_USER_ID = "anonymous"


class WikiRequestScope(StrictBaseModel):
    """Разрешённые границы текущего запроса."""

    company_id: str
    user_id: str
    namespace: str


async def require_scope(container: WikiContainer) -> WikiRequestScope:
    """Компания, пользователь и проверенное пространство запроса."""
    context = get_context()
    if context is None or context.active_company is None:
        raise HTTPException(status_code=403, detail="Компания не выбрана")
    # Анонимный контекст платформы приходит с синтетическим пользователем
    # `anonymous`; для страниц wiki это не читатель, а отсутствие сессии.
    if context.user.user_id in ("", ANONYMOUS_USER_ID):
        raise HTTPException(status_code=403, detail="Пользователь не авторизован")

    raw = (context.active_namespace or "").strip()
    if not raw:
        raise HTTPException(
            status_code=400,
            detail="Не выбрано пространство (X-Platform-Namespace) для wiki",
        )
    if raw == "default":
        _ = await container.namespace_service.ensure_default()
    found = await container.namespace_service.get(raw)
    if found is None:
        raise HTTPException(
            status_code=400,
            detail=f"Пространство «{raw}» не найдено в активной компании",
        )
    if found.company_id != context.active_company.company_id:
        raise HTTPException(status_code=403, detail="Пространство не принадлежит компании")

    return WikiRequestScope(
        company_id=context.active_company.company_id,
        user_id=context.user.user_id,
        namespace=found.name,
    )


async def load_viewable_page(
    container: WikiContainer, scope: WikiRequestScope, wiki_page_id: str
) -> WikiPage:
    """Страница, доступная пользователю на чтение.

    Отсутствие страницы и чужое пространство дают одинаковый 404: разные
    ответы раскрывали бы существование страницы за пределами доступа.
    """
    try:
        return await container.wiki_service.require_viewable_page(
            scope.company_id, scope.namespace, wiki_page_id, scope.user_id
        )
    except WikiPageNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Страница не найдена") from exc
    except WikiAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="Нет доступа к странице") from exc


async def load_editable_page(
    container: WikiContainer, scope: WikiRequestScope, wiki_page_id: str
) -> WikiPage:
    """Страница, доступная пользователю на запись."""
    try:
        return await container.wiki_service.require_editable_page(
            scope.company_id, scope.namespace, wiki_page_id, scope.user_id
        )
    except WikiPageNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Страница не найдена") from exc
    except WikiAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="Нет прав на изменение страницы") from exc


__all__ = [
    "WikiRequestScope",
    "load_editable_page",
    "load_viewable_page",
    "require_scope",
]
