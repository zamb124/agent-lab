"""
API для управления namespaces.
"""

import traceback
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core.config import get_settings
from core.context import get_context
from core.logging import get_logger
from core.models.identity_models import Namespace
from core.rag.factory import get_rag_provider

from ..container import RAGContainer
from ..dependencies import get_container_dep

logger = get_logger(__name__)

router = APIRouter(tags=["namespaces"])


class NamespaceCreateRequest(BaseModel):
    """Запрос на создание namespace"""
    name: str
    description: Optional[str] = None


class NamespaceListResponse(BaseModel):
    """Ответ со списком namespaces"""

    namespaces: List[Namespace]
    company_id: str
    document_status_counts_by_namespace: dict[str, dict[str, int]] = Field(
        default_factory=dict
    )


@router.get("/namespaces", response_model=NamespaceListResponse)
async def list_namespaces(
    provider: Optional[str] = Query(None, description="RAG provider (pgvector, agentset)"),
    container: RAGContainer = Depends(get_container_dep)
) -> NamespaceListResponse:
    """
    Получает список namespaces текущей компании.

    Args:
        provider: Имя провайдера (опционально, по умолчанию используется default_provider)

    Returns:
        Список namespaces компании и имя провайдера
    """
    try:
        context = get_context()
        company_id = context.active_company.company_id

        namespace_repo = container.namespace_repository
        namespaces = await namespace_repo.list_by_company(company_id)

        ns_names = [ns.name for ns in namespaces]
        status_repo = container.document_status_repository
        counts_map = await status_repo.count_effective_document_status_for_namespaces(
            ns_names
        )

        logger.info(f"Получено {len(namespaces)} namespaces для компании {company_id}")

        return NamespaceListResponse(
            namespaces=namespaces,
            company_id=company_id,
            document_status_counts_by_namespace=counts_map,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Ошибка получения namespaces: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list namespaces: {str(e)}")


@router.post("/namespaces", response_model=Namespace, status_code=201)
async def create_namespace(
    request: NamespaceCreateRequest,
    provider: Optional[str] = Query(None, description="RAG provider"),
    container: RAGContainer = Depends(get_container_dep)
) -> Namespace:
    """
    Создает новый namespace для текущей компании.

    Args:
        request: Данные для создания namespace
        provider: Имя провайдера (опционально)

    Returns:
        Созданный namespace
    """
    try:
        context = get_context()
        company_id = context.active_company.company_id

        settings = get_settings()
        if provider is not None:
            rag_provider = get_rag_provider(provider)
            provider_name = provider
        else:
            rag_provider = container.rag_provider
            provider_name = settings.rag.default_provider

        # Провайдер сам добавит company_id через контекст
        await rag_provider.create_namespace(
            name=request.name,
            description=request.description
        )

        namespace_repo = container.namespace_repository
        namespace = Namespace(
            name=request.name,
            company_id=company_id,
            description=request.description,
            provider=provider_name,
        )
        await namespace_repo.set(namespace)

        logger.info(f"Создан namespace: {request.name} для компании {company_id}")

        return namespace
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Ошибка создания namespace: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to create namespace: {str(e)}")


@router.delete("/namespaces/{namespace_id}")
async def delete_namespace(
    namespace_id: str,
    provider: Optional[str] = Query(None, description="RAG provider"),
    container: RAGContainer = Depends(get_container_dep)
):
    """
    Удаляет namespace и все его документы.

    Args:
        namespace_id: ID namespace для удаления
        provider: Имя провайдера (опционально)

    Returns:
        Результат операции
    """
    try:
        context = get_context()
        company_id = context.active_company.company_id

        rag_provider = get_rag_provider(provider) if provider else container.rag_provider
        namespace_repo = container.namespace_repository

        # Удаляем документы из провайдера (может не быть, если namespace пустой)
        provider_deleted = await rag_provider.delete_namespace(namespace_id)

        # Проверяем, существует ли namespace в репозитории
        ns_from_repo = await namespace_repo.get(namespace_id)

        if not provider_deleted and not ns_from_repo:
            raise HTTPException(status_code=404, detail="Namespace not found")

        await namespace_repo.delete(namespace_id)

        logger.info(f"Удален namespace: {namespace_id} для компании {company_id}")

        return {"success": True, "name": namespace_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка удаления namespace: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete namespace: {str(e)}")


