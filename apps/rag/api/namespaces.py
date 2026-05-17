"""
API для управления namespaces.
"""

import asyncio
import traceback
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from apps.rag.config import get_rag_settings
from core.billing.exceptions import BillingBalanceBlockedError
from core.context import require_active_company
from core.logging import get_logger
from core.models.identity_models import Namespace
from core.pagination import OffsetPage
from core.rag.factory import get_rag_provider

from ..dependencies import ContainerDep

logger = get_logger(__name__)

router = APIRouter(tags=["namespaces"])


class NamespaceCreateRequest(BaseModel):
    """Запрос на создание namespace"""
    name: str
    description: Optional[str] = None


@router.get("/namespaces", response_model=OffsetPage[Namespace])
async def list_namespaces(
    container: ContainerDep,
    provider: Optional[str] = Query(None, description="RAG provider (pgvector, agentset)"),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> OffsetPage[Namespace]:
    try:
        company_id = require_active_company().company_id

        namespace_repo = container.namespace_repository
        namespaces, total = await asyncio.gather(
            namespace_repo.list_by_company(company_id, limit=limit, offset=offset),
            namespace_repo.count_all(),
        )

        logger.info(f"Получено {len(namespaces)} namespaces для компании {company_id}")

        return OffsetPage[Namespace](items=namespaces, total=total, limit=limit, offset=offset)
    except BillingBalanceBlockedError:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Ошибка получения namespaces: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list namespaces: {str(e)}")


@router.post("/namespaces", response_model=Namespace, status_code=201)
async def create_namespace(
    request: NamespaceCreateRequest,
    container: ContainerDep,
    provider: Optional[str] = Query(None, description="RAG provider"),
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
        company_id = require_active_company().company_id

        settings = get_rag_settings()
        rag_provider = get_rag_provider(provider, settings=settings) if provider else get_rag_provider(settings=settings)

        # Провайдер сам добавит company_id через контекст
        await rag_provider.create_namespace(
            name=request.name,
            description=request.description
        )

        namespace_repo = container.namespace_repository
        namespace = Namespace(
            name=request.name,
            company_id=company_id,
            description=request.description
        )
        await namespace_repo.set(namespace)

        logger.info(f"Создан namespace: {request.name} для компании {company_id}")

        return namespace
    except BillingBalanceBlockedError:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Ошибка создания namespace: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to create namespace: {str(e)}")


@router.delete("/namespaces/{namespace_id}")
async def delete_namespace(
    namespace_id: str,
    container: ContainerDep,
    provider: Optional[str] = Query(None, description="RAG provider"),
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
        company_id = require_active_company().company_id

        settings = get_rag_settings()
        rag_provider = get_rag_provider(provider, settings=settings) if provider else get_rag_provider(settings=settings)
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
    except BillingBalanceBlockedError:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка удаления namespace: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete namespace: {str(e)}")

