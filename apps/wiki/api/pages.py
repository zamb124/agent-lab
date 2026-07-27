"""
Страницы wiki: дерево, чтение, запись, перемещение, корзина.

Каждый обработчик начинается с `require_scope`: без проверенного пространства
операции не существует.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from apps.wiki.api._scope import load_viewable_page, require_scope
from apps.wiki.content.markdown_parser import WikiMarkdownError, markdown_to_document
from apps.wiki.content.prosemirror import ProseMirrorNode
from apps.wiki.content.schema import WikiSchemaError
from apps.wiki.dependencies import ContainerDep
from apps.wiki.models.api import (
    WikiMarkdownResponse,
    WikiPageContentUpdateRequest,
    WikiPageCreateRequest,
    WikiPageMoveNamespaceRequest,
    WikiPageMoveRequest,
    WikiPagePropertiesUpdateRequest,
    WikiPageResponse,
    WikiTreeResponse,
)
from apps.wiki.models.domain import WikiPageSummary
from apps.wiki.services.wiki_service import WikiAccessDeniedError, WikiPageNotFoundError
from core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/pages", tags=["wiki-pages"])


def _resolve_content(
    content: ProseMirrorNode | None, markdown: str | None
) -> ProseMirrorNode | None:
    """Свести два способа задать содержимое к одному документу.

    Оба поля сразу — ошибка вызывающего: молча выбрать одно из них значит
    потерять то, что человек или агент реально прислал.
    """
    if content is not None and markdown is not None:
        raise HTTPException(
            status_code=400, detail="Укажите либо content, либо markdown, но не оба поля"
        )
    if markdown is None:
        return content
    try:
        return markdown_to_document(markdown)
    except WikiMarkdownError as exc:
        raise HTTPException(status_code=400, detail=f"Markdown не разобран: {exc}") from exc


@router.get("", response_model=WikiTreeResponse)
async def list_tree(container: ContainerDep) -> WikiTreeResponse:
    """Дерево страниц текущего пространства."""
    scope = await require_scope(container)
    items = await container.wiki_service.list_tree(
        scope.company_id, scope.namespace, scope.user_id
    )
    return WikiTreeResponse(namespace=scope.namespace, items=items)


@router.get("/deleted", response_model=WikiTreeResponse)
async def list_deleted(container: ContainerDep) -> WikiTreeResponse:
    scope = await require_scope(container)
    items = await container.wiki_service.list_deleted(
        scope.company_id, scope.namespace, scope.user_id
    )
    return WikiTreeResponse(namespace=scope.namespace, items=items)


@router.post("", response_model=WikiPageResponse, status_code=201)
async def create_page(
    container: ContainerDep, request: WikiPageCreateRequest
) -> WikiPageResponse:
    scope = await require_scope(container)
    content = _resolve_content(request.content, request.markdown)
    try:
        page = await container.wiki_service.create_page(
            company_id=scope.company_id,
            namespace=scope.namespace,
            user_id=scope.user_id,
            title=request.title,
            parent_page_id=request.parent_page_id,
            content=content,
            icon=request.icon,
        )
    except WikiSchemaError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except WikiPageNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Родительская страница не найдена") from exc
    except WikiAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="Нет прав на создание страницы") from exc
    return WikiPageResponse(page=page, can_edit=True, can_administer=True)


@router.get("/{wiki_page_id}", response_model=WikiPageResponse)
async def get_page(container: ContainerDep, wiki_page_id: str) -> WikiPageResponse:
    scope = await require_scope(container)
    page = await load_viewable_page(container, scope, wiki_page_id)
    resolver = await container.wiki_service.build_access_resolver(
        scope.company_id, scope.namespace, scope.user_id
    )
    return WikiPageResponse(
        page=page,
        can_edit=resolver.can_edit(wiki_page_id),
        can_administer=resolver.can_administer(wiki_page_id),
    )


@router.get("/{wiki_page_id}/markdown", response_model=WikiMarkdownResponse)
async def get_page_markdown(
    container: ContainerDep, wiki_page_id: str
) -> WikiMarkdownResponse:
    """Markdown страницы — для экспорта и чтения агентами."""
    scope = await require_scope(container)
    page = await load_viewable_page(container, scope, wiki_page_id)
    return WikiMarkdownResponse(
        wiki_page_id=page.wiki_page_id,
        title=page.title,
        markdown=page.text_markdown,
    )


@router.put("/{wiki_page_id}/content", response_model=WikiPageResponse)
async def update_content(
    container: ContainerDep, wiki_page_id: str, request: WikiPageContentUpdateRequest
) -> WikiPageResponse:
    scope = await require_scope(container)
    content = _resolve_content(request.content, request.markdown)
    if content is None:
        raise HTTPException(status_code=400, detail="Не передано содержимое страницы")
    try:
        page = await container.wiki_service.update_page_content(
            company_id=scope.company_id,
            namespace=scope.namespace,
            user_id=scope.user_id,
            wiki_page_id=wiki_page_id,
            content=content,
            title=request.title,
            create_revision=request.create_revision,
        )
    except WikiSchemaError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except WikiPageNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Страница не найдена") from exc
    except WikiAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="Нет прав на изменение страницы") from exc
    return WikiPageResponse(page=page, can_edit=True, can_administer=False)


@router.patch("/{wiki_page_id}", response_model=WikiPageResponse)
async def update_properties(
    container: ContainerDep, wiki_page_id: str, request: WikiPagePropertiesUpdateRequest
) -> WikiPageResponse:
    scope = await require_scope(container)
    try:
        page = await container.wiki_service.update_page_properties(
            company_id=scope.company_id,
            namespace=scope.namespace,
            user_id=scope.user_id,
            wiki_page_id=wiki_page_id,
            title=request.title,
            icon=request.icon,
            cover_url=request.cover_url,
            is_published=request.is_published,
            is_template=request.is_template,
        )
    except WikiPageNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Страница не найдена") from exc
    except WikiAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="Нет прав на изменение страницы") from exc
    return WikiPageResponse(page=page, can_edit=True, can_administer=False)


@router.post("/{wiki_page_id}/move", response_model=WikiPageResponse)
async def move_page(
    container: ContainerDep, wiki_page_id: str, request: WikiPageMoveRequest
) -> WikiPageResponse:
    scope = await require_scope(container)
    try:
        page = await container.wiki_service.move_page(
            company_id=scope.company_id,
            namespace=scope.namespace,
            user_id=scope.user_id,
            wiki_page_id=wiki_page_id,
            new_parent_page_id=request.parent_page_id,
            position=request.position,
        )
    except WikiPageNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Страница не найдена") from exc
    except WikiAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="Нет прав на перемещение") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return WikiPageResponse(page=page, can_edit=True, can_administer=False)


@router.post("/{wiki_page_id}/move-namespace", response_model=WikiPageResponse)
async def move_page_to_namespace(
    container: ContainerDep, wiki_page_id: str, request: WikiPageMoveNamespaceRequest
) -> WikiPageResponse:
    """Перенести страницу с поддеревом в другое пространство."""
    scope = await require_scope(container)
    target = await container.namespace_service.get(request.target_namespace)
    if target is None or target.company_id != scope.company_id:
        raise HTTPException(status_code=400, detail="Целевое пространство недоступно")

    try:
        page = await container.wiki_service.move_page_to_namespace(
            company_id=scope.company_id,
            namespace=scope.namespace,
            target_namespace=target.name,
            user_id=scope.user_id,
            wiki_page_id=wiki_page_id,
            new_parent_page_id=request.parent_page_id,
        )
    except WikiPageNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Страница не найдена") from exc
    except WikiAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="Нет прав на перенос страницы") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return WikiPageResponse(page=page, can_edit=True, can_administer=False)


@router.delete("/{wiki_page_id}", status_code=204)
async def delete_page(container: ContainerDep, wiki_page_id: str) -> None:
    scope = await require_scope(container)
    try:
        affected = await container.wiki_service.delete_page(
            scope.company_id, scope.namespace, scope.user_id, wiki_page_id
        )
    except WikiPageNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Страница не найдена") from exc
    except WikiAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="Нет прав на удаление") from exc
    logger.info(
        "wiki.page.deleted",
        extra={"wiki_page_id": wiki_page_id, "pages": len(affected)},
    )


@router.post("/{wiki_page_id}/restore", response_model=WikiPageResponse)
async def restore_page(container: ContainerDep, wiki_page_id: str) -> WikiPageResponse:
    scope = await require_scope(container)
    try:
        page = await container.wiki_service.restore_page(
            scope.company_id, scope.namespace, scope.user_id, wiki_page_id
        )
    except WikiPageNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Страница не найдена") from exc
    return WikiPageResponse(page=page, can_edit=True, can_administer=False)


@router.get("/{wiki_page_id}/children", response_model=list[WikiPageSummary])
async def list_children(
    container: ContainerDep,
    wiki_page_id: str,
    include_self: Annotated[bool, Query()] = False,
) -> list[WikiPageSummary]:
    scope = await require_scope(container)
    _ = await load_viewable_page(container, scope, wiki_page_id)
    tree = await container.wiki_service.list_tree(
        scope.company_id, scope.namespace, scope.user_id
    )
    children = [item for item in tree if item.parent_page_id == wiki_page_id]
    if include_self:
        children = [item for item in tree if item.wiki_page_id == wiki_page_id] + children
    return children
