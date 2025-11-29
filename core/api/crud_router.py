"""
Генератор CRUD роутеров для репозиториев.
Автоматически создает стандартные эндпоинты для работы с сущностями.
"""

import logging
from typing import Type, TypeVar, List, Dict, Any, Optional, Callable
from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel
from typing import Annotated

from core.db.base_repository import BaseRepository

logger = logging.getLogger(__name__)

T = TypeVar('T', bound=BaseModel)


class CRUDRouterGenerator:
    """
    Генератор CRUD роутеров для репозиториев.
    
    Автоматически создает стандартные эндпоинты:
    - GET /{prefix} - список всех (с пагинацией)
    - GET /{prefix}/{id} - получить по ID
    - POST /{prefix} - создать/обновить
    - DELETE /{prefix}/{id} - удалить
    - POST /{prefix}/many - получить несколько по ID
    """
    
    def __init__(
        self,
        repository: BaseRepository[T],
        prefix: str,
        tags: List[str],
        repository_dependency: Callable
    ):
        """
        Args:
            repository: Экземпляр репозитория
            prefix: Префикс пути для роутера (например, "/agents")
            tags: Теги для OpenAPI документации
            repository_dependency: Dependency функция для получения репозитория
        """
        self.repository = repository
        self.prefix = prefix
        self.tags = tags
        self.repository_dependency = repository_dependency
        self.model_class = repository.model_class
    
    def generate_router(self) -> APIRouter:
        """
        Генерирует FastAPI роутер с CRUD эндпоинтами.
        
        Returns:
            APIRouter с зарегистрированными эндпоинтами
        """
        router = APIRouter(
            prefix=self.prefix,
            tags=self.tags
        )
        
        RepositoryDep = Annotated[BaseRepository[T], Depends(self.repository_dependency)]
        
        @router.get("", response_model=List[Dict[str, Any]])
        async def list_entities(
            repository: RepositoryDep,
            limit: int = Query(100, ge=1, le=1000, description="Максимальное количество результатов"),
            offset: int = Query(0, ge=0, description="Смещение для пагинации")
        ):
            """
            Получить список всех сущностей.
            
            Returns:
                Список сущностей с пагинацией
            """
            all_entities = await repository.list_all(limit=limit + offset)
            
            if offset > 0:
                entities = all_entities[offset:]
            else:
                entities = all_entities
            
            return [entity.model_dump() for entity in entities[:limit]]
        
        @router.get("/{entity_id}", response_model=Dict[str, Any])
        async def get_entity(
            entity_id: str,
            repository: RepositoryDep
        ):
            """
            Получить сущность по ID.
            
            Args:
                entity_id: Идентификатор сущности
                
            Returns:
                Сущность
            """
            entity = await repository.get(entity_id)
            
            if not entity:
                raise HTTPException(
                    status_code=404,
                    detail=f"Entity with id '{entity_id}' not found"
                )
            
            return entity.model_dump()
        
        @router.post("", response_model=Dict[str, Any])
        async def create_or_update_entity(
            entity_data: Dict[str, Any],
            repository: RepositoryDep
        ):
            """
            Создать или обновить сущность.
            
            Args:
                entity_data: Данные сущности (JSON)
                
            Returns:
                Созданная/обновленная сущность
            """
            try:
                entity = self.model_class.model_validate(entity_data)
            except Exception as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid entity data: {str(e)}"
                )
            
            success = await repository.set(entity)
            
            if not success:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to save entity"
                )
            
            return entity.model_dump()
        
        @router.delete("/{entity_id}")
        async def delete_entity(
            entity_id: str,
            repository: RepositoryDep
        ):
            """
            Удалить сущность по ID.
            
            Args:
                entity_id: Идентификатор сущности
                
            Returns:
                Результат удаления
            """
            success = await repository.delete(entity_id)
            
            if not success:
                raise HTTPException(
                    status_code=404,
                    detail=f"Entity with id '{entity_id}' not found"
                )
            
            return {
                "success": True,
                "entity_id": entity_id,
                "message": "Entity deleted successfully"
            }
        
        @router.post("/many", response_model=Dict[str, Dict[str, Any]])
        async def get_many_entities(
            entity_ids: List[str],
            repository: RepositoryDep
        ):
            """
            Получить несколько сущностей по списку ID.
            
            Args:
                entity_ids: Список идентификаторов
                
            Returns:
                Словарь {entity_id: entity}
            """
            if not entity_ids:
                return {}
            
            entities = await repository.get_many(entity_ids)
            
            return {
                entity_id: entity.model_dump()
                for entity_id, entity in entities.items()
            }
        
        return router

