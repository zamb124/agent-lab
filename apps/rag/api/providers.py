"""
API для управления RAG провайдерами.
"""

from fastapi import APIRouter, HTTPException

from apps.rag.config import get_rag_settings
from core.logging import get_logger
from core.models import StrictBaseModel
from core.pagination import ListResponse
from core.rag.factory import get_rag_provider

logger = get_logger(__name__)

router = APIRouter(tags=["providers"])


class ProviderInfo(StrictBaseModel):
    """Информация о RAG провайдере"""

    name: str
    enabled: bool
    is_default: bool
    type: str


class ProvidersView(ListResponse[ProviderInfo]):
    """Композитный ответ: канонический `items` из core.pagination +
    метаполе `current_provider` (имя активного провайдера для компании).

    Наследуется от ``ListResponse[ProviderInfo]`` — не ad-hoc модель
    пагинации, а расширение канонической формы дополнительным полем
    (см. правило «только CursorPage/OffsetPage/ListResponse» в main.mdc).
    """

    current_provider: str


class ProviderSwitchRequest(StrictBaseModel):
    """Запрос на переключение провайдера"""

    provider_name: str


class ProviderSwitchResponse(StrictBaseModel):
    """Ответ переключения RAG провайдера."""

    success: bool
    provider: str
    message: str


@router.get("/providers", response_model=ProvidersView)
async def list_providers() -> ProvidersView:
    """
    Возвращает список доступных RAG провайдеров.

    Возвращает:
        Список провайдеров с их статусом и текущий активный провайдер
    """
    settings = get_rag_settings()

    if not settings.rag.enabled:
        raise HTTPException(status_code=503, detail="RAG is disabled")

    providers: list[ProviderInfo] = []
    for name, config in settings.rag.providers.items():
        if config.enabled:
            providers.append(
                ProviderInfo(
                    name=name,
                    enabled=True,
                    is_default=(name == settings.rag.default_provider),
                    type=name,
                )
            )

    logger.info(f"Список провайдеров запрошен: {[p.name for p in providers]}")

    return ProvidersView(
        items=providers,
        current_provider=settings.rag.default_provider,
    )


@router.post("/providers/switch", response_model=ProviderSwitchResponse)
async def switch_provider(
    request: ProviderSwitchRequest,
) -> ProviderSwitchResponse:
    """
    Переключает активный RAG провайдер.

    ВАЖНО: Это переключение действует только в рамках текущей сессии.
    Для постоянного изменения нужно обновить конфигурацию.
    """
    try:
        settings = get_rag_settings()
        _ = get_rag_provider(request.provider_name, settings=settings)
        logger.info(f"Провайдер переключен на: {request.provider_name}")
        return ProviderSwitchResponse(
            success=True,
            provider=request.provider_name,
            message=f"Switched to {request.provider_name}",
        )
    except ValueError as e:
        logger.error(f"Ошибка переключения провайдера: {e}")
        raise HTTPException(status_code=400, detail=str(e))

