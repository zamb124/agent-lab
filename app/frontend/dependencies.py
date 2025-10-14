"""
Dependency Injection для фронтенда

Общие зависимости для API роутеров
"""

from typing import Annotated
from fastapi import Depends

from app.db.repositories import Storage, AgentRepository, FlowRepository, TaskRepository, SessionRepository, ToolRepository
from app.core.container import get_container
from app.core.context import get_context
from app.models import Context
from app.frontend.services.canvas_service import CanvasService


async def get_storage() -> Storage:
    """
    Получить Storage из контейнера
    
    Usage:
        @router.get("/")
        async def endpoint(storage: Storage = Depends(get_storage)):
            ...
    """
    container = get_container()
    return container.get_storage()


async def get_agent_repository() -> AgentRepository:
    """Получить AgentRepository из контейнера"""
    container = get_container()
    return container.get_agent_repository()


async def get_flow_repository() -> FlowRepository:
    """Получить FlowRepository из контейнера"""
    container = get_container()
    return container.get_flow_repository()


async def get_task_repository() -> TaskRepository:
    """Получить TaskRepository из контейнера"""
    container = get_container()
    return container.get_task_repository()


async def get_session_repository() -> SessionRepository:
    """Получить SessionRepository из контейнера"""
    container = get_container()
    return container.get_session_repository()


async def get_tool_repository() -> ToolRepository:
    """Получить ToolRepository из контейнера"""
    container = get_container()
    return container.get_tool_repository()


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
