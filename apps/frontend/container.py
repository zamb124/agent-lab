"""
FrontendContainer - DI контейнер для сервиса фронтенда.

Наследуется от BaseContainer и добавляет сервисы через @lazy декоратор.
"""

import logging
from typing import Optional, Any

from core.container import BaseContainer, lazy

logger = logging.getLogger(__name__)


# Маппинг model_type -> атрибут репозитория в контейнере
MODEL_TYPE_TO_REPOSITORY = {
    "agent": "agent_repository",
    "flow": "flow_repository",
    "tool": "tool_repository",
    "user": "user_repository",
    "session": "session_repository",
}


class FrontendContainer(BaseContainer):
    """
    Контейнер для сервиса фронтенда.
    
    Репозитории agents-сервиса автоматически проксируются через HTTP,
    так как owner_service="agents" != service_name="frontend".
    
    Пример:
        container = get_frontend_container()
        agent = await container.agent_repository.get("agent_id")  # HTTP запрос к agents
    """
    
    @lazy
    def canvas_service(self):
        from apps.frontend.services.canvas_service import CanvasService
        return CanvasService()
    
    @lazy
    def agent_repository(self):
        """AgentRepository - HTTP прокси к сервису agents"""
        from apps.agents.db.repositories import AgentRepository
        return self._get_repository(AgentRepository)
    
    @lazy
    def flow_repository(self):
        """FlowRepository - HTTP прокси к сервису agents"""
        from apps.agents.db.repositories import FlowRepository
        return self._get_repository(FlowRepository)
    
    @lazy
    def tool_repository(self):
        """ToolRepository - HTTP прокси к сервису agents"""
        from apps.agents.db.repositories import ToolRepository
        return self._get_repository(ToolRepository)
    
    @lazy
    def session_repository(self):
        """SessionRepository - HTTP прокси к сервису agents"""
        from apps.agents.db.repositories import SessionRepository
        return self._get_repository(SessionRepository)
    
    @lazy
    def rag_repository(self):
        """RAGRepository - работа с RAG документами"""
        from core.rag import RAGRepository
        return RAGRepository()
    
    def get_repository_by_model_type(self, model_type: str) -> Any:
        """
        Получить репозиторий по типу модели.
        
        Args:
            model_type: Тип модели (agent, flow, tool, task, user, session)
            
        Returns:
            Репозиторий для данного типа модели
            
        Raises:
            ValueError: Если для данного типа нет репозитория
        """
        repo_attr = MODEL_TYPE_TO_REPOSITORY.get(model_type)
        if not repo_attr:
            raise ValueError(
                f"Тип модели '{model_type}' не имеет репозитория. "
                f"Доступные типы: {list(MODEL_TYPE_TO_REPOSITORY.keys())}. "
                f"Для вложенных объектов (llm_config, graph_definition) используйте show_inline_modal."
            )
        return getattr(self, repo_attr)


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
