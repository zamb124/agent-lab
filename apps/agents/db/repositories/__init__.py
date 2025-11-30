"""
Репозитории для сервиса agents.
"""

import os


def get_agents_service_url() -> str:
    """
    URL сервиса agents.
    Для тестов использует переменные окружения AGENTS_SERVICE_HOST/PORT.
    Для production использует settings.server.get_service_url().
    """
    host = os.environ.get("AGENTS_SERVICE_HOST")
    port = os.environ.get("AGENTS_SERVICE_PORT")
    if host and port:
        return f"http://{host}:{port}"
    from core.config import get_settings
    return get_settings().server.get_service_url()


from apps.agents.db.repositories.agent_repository import AgentRepository
from apps.agents.db.repositories.flow_repository import FlowRepository
from apps.agents.db.repositories.tool_repository import ToolRepository
from apps.agents.db.repositories.task_repository import TaskRepository
from apps.agents.db.repositories.session_repository import SessionRepository
from apps.agents.db.repositories.mcp_repository import MCPServerRepository
from apps.agents.db.repositories.store_repository import StoreRepository
from apps.agents.db.repositories.agent_state_repository import AgentStateRepository

__all__ = [
    "get_agents_service_url",
    "AgentRepository",
    "FlowRepository",
    "ToolRepository",
    "TaskRepository",
    "SessionRepository",
    "MCPServerRepository",
    "StoreRepository",
    "AgentStateRepository",
]
