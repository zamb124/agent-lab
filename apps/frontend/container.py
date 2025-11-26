"""
FrontendContainer - DI контейнер для сервиса фронтенда.

Наследуется от BaseContainer и добавляет:
- Frontend-специфичные сервисы (CanvasService)
- Доступ к AgentsContainer для получения агентов, flows, tools

Поддерживает:
- shared БД (shared_db) - для users, companies, files, sessions
- Использует AgentsContainer для работы с agents, flows, tools
"""

import logging
from typing import Optional, TYPE_CHECKING

from core.container import BaseContainer
from core.db.storage import Storage
from core.context import get_context

if TYPE_CHECKING:
    from apps.frontend.services.canvas_service import CanvasService

logger = logging.getLogger(__name__)


class FrontendContainer(BaseContainer):
    """
    Контейнер для сервиса фронтенда.
    
    Расширяет BaseContainer добавляя frontend-специфичные сервисы.
    Использует AgentsContainer для доступа к агентам, flows, tools.
    """

    def __init__(self, service_db_url: Optional[str] = None, shared_db_url: Optional[str] = None):
        """
        Args:
            service_db_url: URL БД для сервиса (может быть такой же как shared для frontend)
            shared_db_url: URL shared БД (users, companies, files, sessions)
        """
        super().__init__(db_url=service_db_url or shared_db_url)
        
        self.shared_db_url = shared_db_url
        self._shared_storage: Optional[Storage] = None
        self._canvas_service: Optional["CanvasService"] = None

    def __getattr__(self, name: str):
        """Ленивая инициализация сервисов"""
        
        if name == 'shared_storage':
            if self._shared_storage is None:
                self._shared_storage = Storage(db_url=self.shared_db_url, get_context_func=get_context)
                logger.debug("Shared Storage инициализирован")
            return self._shared_storage
        
        if name == 'canvas_service':
            if self._canvas_service is None:
                from apps.frontend.services.canvas_service import CanvasService
                self._canvas_service = CanvasService()
                logger.debug("CanvasService инициализирован")
            return self._canvas_service
        
        return super().__getattr__(name)

    def get_agents_container(self):
        """Получить AgentsContainer для доступа к агентам, flows, tools"""
        try:
            from apps.agents.container import get_agents_container
            return get_agents_container()
        except RuntimeError:
            logger.warning("AgentsContainer не инициализирован. Некоторые функции могут быть недоступны.")
            return None


_frontend_container: Optional[FrontendContainer] = None


def get_frontend_container() -> FrontendContainer:
    """Получает контейнер сервиса фронтенда"""
    global _frontend_container
    if _frontend_container is None:
        raise RuntimeError("FrontendContainer не инициализирован! Вызовите set_frontend_container() при старте приложения.")
    return _frontend_container


def set_frontend_container(container: FrontendContainer) -> None:
    """Устанавливает контейнер сервиса фронтенда"""
    global _frontend_container
    _frontend_container = container
    logger.info("FrontendContainer установлен")


get_container = get_frontend_container

