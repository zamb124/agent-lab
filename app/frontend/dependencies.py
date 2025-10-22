"""
Dependency Injection для фронтенда

Общие зависимости для API роутеров
"""

from typing import Annotated, Any, TYPE_CHECKING
from fastapi import Depends

from app.db.repositories import Storage, AgentRepository, FlowRepository, TaskRepository, SessionRepository, ToolRepository
from app.core.container import get_container
from app.core.context import get_context
from app.models import Context
from app.frontend.services.canvas_service import CanvasService
from app.services.variables_service import VariablesService
from app.interfaces.factory import InterfaceFactory

if TYPE_CHECKING:
    from app.identity.auth_service import AuthService


async def get_storage() -> Storage:
    """
    Получить Storage из контейнера
    
    Usage:
        @router.get("/")
        async def endpoint(storage: Storage = Depends(get_storage)):
            ...
    """
    container = get_container()
    return container.storage


async def get_agent_repository() -> AgentRepository:
    """Получить AgentRepository из контейнера"""
    container = get_container()
    return container.agent_repository


async def get_flow_repository() -> FlowRepository:
    """Получить FlowRepository из контейнера"""
    container = get_container()
    return container.flow_repository


async def get_task_repository() -> TaskRepository:
    """Получить TaskRepository из контейнера"""
    container = get_container()
    return container.task_repository


async def get_session_repository() -> SessionRepository:
    """Получить SessionRepository из контейнера"""
    container = get_container()
    return container.session_repository


async def get_tool_repository() -> ToolRepository:
    """Получить ToolRepository из контейнера"""
    container = get_container()
    return container.tool_repository


async def get_variables_service() -> VariablesService:
    """Получить VariablesService из контейнера"""
    container = get_container()
    return container.variables_service


async def get_interface_factory() -> InterfaceFactory:
    """Получить InterfaceFactory из контейнера"""
    container = get_container()
    return container.interface_factory


async def get_auth_service() -> "AuthService":
    """Получить AuthService из контейнера"""
    container = get_container()
    return container.auth_service


async def get_canvas_service(
    storage: Annotated[Storage, Depends(get_storage)]
) -> CanvasService:
    """
    Получить Canvas Service с автоматической инъекцией Storage
    
    Usage:
        @router.put("/canvas")
        async def update(service: CanvasService = Depends(get_canvas_service)):
            ...
    """
    return CanvasService(storage)


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


StorageDep = Annotated[Storage, Depends(get_storage)]
CanvasServiceDep = Annotated[CanvasService, Depends(get_canvas_service)]
ContextDep = Annotated[Context, Depends(get_request_context)]
AgentRepositoryDep = Annotated[AgentRepository, Depends(get_agent_repository)]
FlowRepositoryDep = Annotated[FlowRepository, Depends(get_flow_repository)]
TaskRepositoryDep = Annotated[TaskRepository, Depends(get_task_repository)]
SessionRepositoryDep = Annotated[SessionRepository, Depends(get_session_repository)]
ToolRepositoryDep = Annotated[ToolRepository, Depends(get_tool_repository)]
VariablesServiceDep = Annotated[VariablesService, Depends(get_variables_service)]
InterfaceFactoryDep = Annotated[InterfaceFactory, Depends(get_interface_factory)]
AuthServiceDep = Annotated["AuthService", Depends(get_auth_service)]
