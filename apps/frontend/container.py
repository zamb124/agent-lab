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
    "task": "task_repository",
    "user": "user_repository",
    "session": "session_repository",
}


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
    
    @lazy
    def agent_repository(self):
        """AgentRepository - проксируется из AgentsContainer"""
        from apps.agents.container import get_agents_container
        return get_agents_container().agent_repository
    
    @lazy
    def flow_repository(self):
        """FlowRepository - проксируется из AgentsContainer"""
        from apps.agents.container import get_agents_container
        return get_agents_container().flow_repository
    
    @lazy
    def tool_repository(self):
        """ToolRepository - проксируется из AgentsContainer"""
        from apps.agents.container import get_agents_container
        return get_agents_container().tool_repository
    
    @lazy
    def task_repository(self):
        """TaskRepository - проксируется из AgentsContainer"""
        from apps.agents.container import get_agents_container
        return get_agents_container().task_repository
    
    @lazy
    def session_repository(self):
        """SessionRepository - проксируется из AgentsContainer"""
        from apps.agents.container import get_agents_container
        return get_agents_container().session_repository
    
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
