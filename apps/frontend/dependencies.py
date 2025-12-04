"""
Dependency Injection для фронтенда

Общие зависимости для API роутеров
"""

from typing import Annotated
from fastapi import Depends

from core.context import get_context
from core.models.context_models import Context
from apps.frontend.container import get_frontend_container
from apps.frontend.services.canvas_service import CanvasService
from apps.agents.container import get_agents_container
from apps.agents.db.repositories.agent_repository import AgentRepository
from apps.agents.db.repositories.flow_repository import FlowRepository
from apps.agents.db.repositories.session_repository import SessionRepository
from apps.agents.db.repositories.tool_repository import ToolRepository
from core.variables import VariablesService
from core.identity.auth_service import AuthService
from apps.agents.interfaces.factory import InterfaceFactory
from core.rag import RAGRepository


async def get_agent_repository() -> AgentRepository:
    """Получить AgentRepository из AgentsContainer"""
    container = get_agents_container()
    return container.agent_repository


async def get_flow_repository() -> FlowRepository:
    """Получить FlowRepository из AgentsContainer"""
    container = get_agents_container()
    return container.flow_repository


async def get_session_repository() -> SessionRepository:
    """Получить SessionRepository из AgentsContainer"""
    container = get_agents_container()
    return container.session_repository


async def get_tool_repository() -> ToolRepository:
    """Получить ToolRepository из AgentsContainer"""
    container = get_agents_container()
    return container.tool_repository


async def get_variables_service() -> VariablesService:
    """Получить VariablesService из AgentsContainer"""
    container = get_agents_container()
    return container.variables_service


async def get_interface_factory() -> InterfaceFactory:
    """Получить InterfaceFactory из AgentsContainer"""
    container = get_agents_container()
    return container.interface_factory


async def get_auth_service() -> AuthService:
    """Получить AuthService из контейнера"""
    container = get_frontend_container()
    return container.auth_service


async def get_rag_repository() -> RAGRepository:
    """Получить RAGRepository из контейнера"""
    container = get_frontend_container()
    return container.rag_repository


async def get_canvas_service() -> CanvasService:
    """
    Получить Canvas Service из контейнера
    
    Usage:
        @router.put("/canvas")
        async def update(service: CanvasService = Depends(get_canvas_service)):
            ...
    """
    container = get_frontend_container()
    return container.canvas_service


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


CanvasServiceDep = Annotated[CanvasService, Depends(get_canvas_service)]
ContextDep = Annotated[Context, Depends(get_request_context)]
AgentRepositoryDep = Annotated[AgentRepository, Depends(get_agent_repository)]
FlowRepositoryDep = Annotated[FlowRepository, Depends(get_flow_repository)]
SessionRepositoryDep = Annotated[SessionRepository, Depends(get_session_repository)]
ToolRepositoryDep = Annotated[ToolRepository, Depends(get_tool_repository)]
VariablesServiceDep = Annotated[VariablesService, Depends(get_variables_service)]
InterfaceFactoryDep = Annotated[InterfaceFactory, Depends(get_interface_factory)]
AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
RAGRepositoryDep = Annotated[RAGRepository, Depends(get_rag_repository)]
