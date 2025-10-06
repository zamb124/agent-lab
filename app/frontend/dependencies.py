"""
Dependency Injection для фронтенда

Общие зависимости для API роутеров
"""

from typing import Annotated
from fastapi import Depends

from app.core.storage import Storage
from app.core.container import get_container
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


StorageDep = Annotated[Storage, Depends(get_storage)]
CanvasServiceDep = Annotated[CanvasService, Depends(get_canvas_service)]
