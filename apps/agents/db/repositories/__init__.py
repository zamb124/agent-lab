"""
Репозитории для сервиса agents.
"""

import os


def get_agents_service_url() -> str:
    """
    URL сервиса agents.
    Приоритет:
    1. TEST_AGENTS_SERVICE_URL (env) - для тестов
    2. AGENTS_SERVICE_URL (env) - для docker-compose
    3. settings.server.agents_service_url - из конфига
    4. settings.server.get_service_url() - по умолчанию
    """
    test_url = os.environ.get("TEST_AGENTS_SERVICE_URL")
    if test_url:
        return test_url
    
    env_url = os.environ.get("AGENTS_SERVICE_URL")
    if env_url:
        return env_url
    
    from core.config import get_settings
    return get_settings().server.get_agents_service_url()


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
