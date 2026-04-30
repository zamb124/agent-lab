"""
Генератор CRUD роутеров для репозиториев.
Автоматически создает эндпоинты для ВСЕХ методов репозитория.
"""

from core.logging import get_logger
import inspect
from typing import TypeVar, List, Dict, Any, Callable
from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel
from typing import Annotated

from core.db.base_repository import BaseRepository
from core.pagination import ListResponse

logger = get_logger(__name__)
T = TypeVar('T', bound=BaseModel)

# Методы которые не нужно экспонировать как API
EXCLUDED_METHODS = {
    '_get_key', '_get_prefix', '_get_table_name', '_extract_entity_id',
    '_build_final_key', 'get_service_url'
}

class CRUDRouterGenerator:
    """
    Генератор роутеров для репозиториев.
    
    Автоматически создает эндпоинты для ВСЕХ публичных методов репозитория:
    - Стандартные CRUD (get, set, delete, list, get_many) - оптимизированные пути
    - Любые другие методы - через POST /method/{method_name}
    """
    
    def __init__(
        self,
        repository: BaseRepository[T],
        prefix: str,
        tags: List[str],
        repository_dependency: Callable
    ):
        self._repository = repository
        self._prefix = prefix
        self._tags = tags
        self._repository_dependency = repository_dependency
        self._model_class = repository.model_class
    
    def generate_router(self) -> APIRouter:
        """Генерирует FastAPI роутер с эндпоинтами для всех методов репозитория"""
        router = APIRouter(prefix=self._prefix, tags=self._tags)
        
        RepositoryDep = Annotated[BaseRepository[T], Depends(self._repository_dependency)]
        
        # Стандартные CRUD эндпоинты (оптимизированные)
        self._add_standard_crud(router, RepositoryDep)
        
        # Динамические эндпоинты для всех остальных методов
        self._add_dynamic_methods(router, RepositoryDep)
        
        return router
    
    def _add_standard_crud(self, router: APIRouter, RepositoryDep):
        """Добавляет стандартные CRUD эндпоинты"""
        
        @router.get("", response_model=ListResponse[Dict[str, Any]])
        async def list_entities(
            repository: RepositoryDep,
            limit: int = Query(100, ge=1, le=1000),
            offset: int = Query(0, ge=0)
        ):
            """Получить страницу сущностей."""
            entities = await repository.list(limit=limit, offset=offset)
            return ListResponse[Dict[str, Any]](items=[entity.model_dump() for entity in entities])
        
        @router.get("/{entity_id}", response_model=Dict[str, Any])
        async def get_entity(entity_id: str, repository: RepositoryDep):
            """Получить сущность по ID"""
            entity = await repository.get(entity_id)
            if not entity:
                raise HTTPException(status_code=404, detail=f"Entity '{entity_id}' not found")
            return entity.model_dump()
        
        @router.post("", response_model=Dict[str, Any])
        async def create_or_update_entity(entity_data: Dict[str, Any], repository: RepositoryDep):
            """Создать или обновить сущность"""
            try:
                entity = self._model_class.model_validate(entity_data)
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Invalid data: {str(e)}")
            
            success = await repository.set(entity)
            if not success:
                raise HTTPException(status_code=500, detail="Failed to save")
            return entity.model_dump()
        
        @router.delete("/{entity_id}")
        async def delete_entity(entity_id: str, repository: RepositoryDep):
            """Удалить сущность по ID"""
            success = await repository.delete(entity_id)
            if not success:
                raise HTTPException(status_code=404, detail=f"Entity '{entity_id}' not found")
            return {"success": True, "entity_id": entity_id}
        
        @router.post("/many", response_model=Dict[str, Dict[str, Any]])
        async def get_many_entities(entity_ids: List[str], repository: RepositoryDep):
            """Получить несколько сущностей по ID"""
            if not entity_ids:
                return {}
            entities = await repository.get_many(entity_ids)
            return {eid: entity.model_dump() for eid, entity in entities.items()}
    
    def _add_dynamic_methods(self, router: APIRouter, RepositoryDep):
        """Добавляет эндпоинты для всех кастомных методов репозитория"""
        
        # Находим все публичные async методы
        for name, method in inspect.getmembers(self.repository, predicate=inspect.ismethod):
            if name.startswith('_') or name in EXCLUDED_METHODS:
                continue
            
            # Пропускаем стандартные CRUD методы (уже добавлены оптимизированно)
            if name in {'get', 'set', 'delete', 'list', 'get_many'}:
                continue
            
            # Проверяем что это async метод
            if not inspect.iscoroutinefunction(method):
                continue
            
            self._add_method_endpoint(router, name, method, RepositoryDep)
    
    def _add_method_endpoint(
        self,
        router: APIRouter,
        method_name: str,
        method: Callable,
        RepositoryDep
    ):
        """Создает эндпоинт для конкретного метода репозитория"""
        
        # Получаем сигнатуру метода для документации
        sig = inspect.signature(method)
        params = list(sig.parameters.keys())
        if params and params[0] == 'self':
            params = params[1:]
        
        async def method_handler(
            payload: Dict[str, Any],
            repository: RepositoryDep
        ):
            """Универсальный обработчик для метода репозитория"""
            args = payload.get("args", [])
            kwargs = payload.get("kwargs", {})
            
            repo_method = getattr(repository, method_name, None)
            if not repo_method:
                raise HTTPException(
                    status_code=404,
                    detail=f"Method '{method_name}' not found"
                )
            
            try:
                result = await repo_method(*args, **kwargs)
            except TypeError as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid arguments for '{method_name}': {str(e)}"
                )
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=f"Error in '{method_name}': {str(e)}"
                )
            
            # Сериализуем результат
            if result is None:
                return None
            if isinstance(result, BaseModel):
                return result.model_dump()
            if isinstance(result, list):
                return [
                    item.model_dump() if isinstance(item, BaseModel) else item
                    for item in result
                ]
            if isinstance(result, dict):
                return {
                    k: v.model_dump() if isinstance(v, BaseModel) else v
                    for k, v in result.items()
                }
            return result
        
        # Регистрируем эндпоинт
        router.add_api_route(
            f"/method/{method_name}",
            method_handler,
            methods=["POST"],
            summary=f"Call {method_name}",
            description=f"Вызов метода {method_name}. Параметры: {params}"
        )
        
        logger.debug(f"Зарегистрирован эндпоинт: POST /method/{method_name}")
