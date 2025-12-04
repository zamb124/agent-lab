"""
Dependency Injection для сервиса агентов

Общие зависимости для API роутеров
"""

from typing import Annotated, Dict, Callable, Any
from fastapi import Depends

from apps.agents.db.repositories import AgentRepository, FlowRepository, SessionRepository, ToolRepository
from apps.agents.container import get_agents_container
from core.context import get_context
from core.models import Context
from core.variables import VariablesService
from core.identity.auth_service import AuthService
from apps.agents.interfaces.factory import InterfaceFactory
from core.db.storage import Storage

_repository_dependencies: Dict[str, Callable] = {}


async def get_storage() -> Storage:
    """
    Получить Storage из контейнера (deprecated, для совместимости с тестами)
    
    DEPRECATED: Используйте репозитории вместо прямого доступа к Storage
    """
    container = get_agents_container()
    return container.storage


async def get_agent_repository() -> AgentRepository:
    """Получить AgentRepository из контейнера"""
    container = get_agents_container()
    return container.agent_repository


async def get_flow_repository() -> FlowRepository:
    """Получить FlowRepository из контейнера"""
    container = get_agents_container()
    return container.flow_repository


async def get_session_repository() -> SessionRepository:
    """Получить SessionRepository из контейнера"""
    container = get_agents_container()
    return container.session_repository


async def get_tool_repository() -> ToolRepository:
    """Получить ToolRepository из контейнера"""
    container = get_agents_container()
    return container.tool_repository


async def get_variables_service() -> VariablesService:
    """Получить VariablesService из контейнера"""
    container = get_agents_container()
    return container.variables_service


async def get_interface_factory() -> InterfaceFactory:
    """Получить InterfaceFactory из контейнера"""
    container = get_agents_container()
    return container.interface_factory


async def get_auth_service() -> AuthService:
    """Получить AuthService из контейнера"""
    container = get_agents_container()
    return container.auth_service


async def get_request_context() -> Context:
    """
    Получить контекст текущего запроса из middleware.
    Гарантированно есть для всех /api/v1/ и /frontend/ роутов.
    
    Usage:
        @router.get("/")
        async def endpoint(context: Context = Depends(get_request_context)):
            user = context.user
            company = context.active_company
            ...
    """
    return get_context()


def generate_repository_dependency(repository_name: str, repository_class: type) -> Callable:
    """
    Генерирует dependency функцию для репозитория.
    
    Args:
        repository_name: Имя репозитория (например, "agent_repository")
        repository_class: Класс репозитория
        
    Returns:
        Dependency функция
    """
    async def get_repository():
        container = get_agents_container()
        return getattr(container, repository_name)
    
    get_repository.__name__ = f"get_{repository_name}"
    _repository_dependencies[repository_name] = get_repository
    
    return get_repository


def get_repository_dependency(repository_name: str) -> Callable:
    """
    Получает dependency функцию для репозитория.
    
    Args:
        repository_name: Имя репозитория
        
    Returns:
        Dependency функция
    """
    if repository_name not in _repository_dependencies:
        raise ValueError(f"Dependency для {repository_name} не найдена")
    return _repository_dependencies[repository_name]


ContextDep = Annotated[Context, Depends(get_request_context)]
AgentRepositoryDep = Annotated[AgentRepository, Depends(get_agent_repository)]
FlowRepositoryDep = Annotated[FlowRepository, Depends(get_flow_repository)]
SessionRepositoryDep = Annotated[SessionRepository, Depends(get_session_repository)]
ToolRepositoryDep = Annotated[ToolRepository, Depends(get_tool_repository)]
VariablesServiceDep = Annotated[VariablesService, Depends(get_variables_service)]
InterfaceFactoryDep = Annotated[InterfaceFactory, Depends(get_interface_factory)]
AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
