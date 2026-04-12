"""
API для управления RAG провайдерами.
"""

from typing import List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.logging import get_logger
from core.config import get_settings
from core.rag.factory import get_rag_provider
from ..dependencies import ContainerDep

logger = get_logger(__name__)

router = APIRouter(tags=["providers"])


class ProviderInfo(BaseModel):
    """Информация о RAG провайдере"""
    name: str
    enabled: bool
    is_default: bool
    type: str


class ProviderListResponse(BaseModel):
    """Ответ со списком провайдеров"""
    items: List[ProviderInfo]
    current_provider: str


class ProviderSwitchRequest(BaseModel):
    """Запрос на переключение провайдера"""
    provider_name: str


@router.get("/providers", response_model=ProviderListResponse)
async def list_providers(
    container: ContainerDep,
) -> ProviderListResponse:
    """
    Возвращает список доступных RAG провайдеров.
    
    Returns:
        Список провайдеров с их статусом и текущий активный провайдер
    """
    settings = get_settings()
    
    if not settings.rag.enabled:
        raise HTTPException(status_code=503, detail="RAG is disabled")
    
    providers = []
    for name, config in settings.rag.providers.items():
        if config.enabled:
            providers.append(ProviderInfo(
                name=name,
                enabled=True,
                is_default=(name == settings.rag.default_provider),
                type=name
            ))
    
    logger.info(f"Список провайдеров запрошен: {[p.name for p in providers]}")
    
    return ProviderListResponse(
        items=providers,
        current_provider=settings.rag.default_provider
    )


@router.post("/providers/switch")
async def switch_provider(
    request: ProviderSwitchRequest,
    container: ContainerDep,
):
    """
    Переключает активный RAG провайдер.
    
    ВАЖНО: Это переключение действует только в рамках текущей сессии.
    Для постоянного изменения нужно обновить конфигурацию.
    """
    try:
        provider = get_rag_provider(request.provider_name)
        logger.info(f"Провайдер переключен на: {request.provider_name}")
        return {
            "success": True,
            "provider": request.provider_name,
            "message": f"Switched to {request.provider_name}"
        }
    except ValueError as e:
        logger.error(f"Ошибка переключения провайдера: {e}")
        raise HTTPException(status_code=400, detail=str(e))


