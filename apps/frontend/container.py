"""
FrontendContainer - DI контейнер для сервиса фронтенда.

Наследуется от BaseContainer и добавляет сервисы через @lazy декоратор.
"""

import logging
from typing import Optional

from core.container import BaseContainer, lazy

logger = logging.getLogger(__name__)


class FrontendContainer(BaseContainer):
    """
    Контейнер для сервиса фронтенда.
    
    Пример:
        container = get_frontend_container()
        user = await container.user_repository.get("user_id")
    """
    
    @lazy
    def canvas_service(self):
        from apps.frontend.services.canvas_service import CanvasService
        return CanvasService()


# === Глобальный контейнер ===

_frontend_container: Optional[FrontendContainer] = None


def get_frontend_container() -> FrontendContainer:
    """Получает контейнер (создает при первом вызове)"""
    global _frontend_container
    if _frontend_container is None:
        from core.config import get_settings
        settings = get_settings()
        _frontend_container = FrontendContainer(
            service_db_url=settings.database.url,
            shared_db_url=settings.database.shared_url
        )
        logger.info("FrontendContainer инициализирован")
    return _frontend_container


# Алиас
get_container = get_frontend_container
