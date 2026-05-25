"""
Генератор CRUD роутеров для репозиториев.
Автоматически создает стандартные CRUD эндпоинты репозитория.
"""

from collections.abc import Callable, Sequence
from enum import Enum
from typing import Annotated, Generic, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from core.db.base_repository import BaseRepository
from core.logging import get_logger
from core.pagination import ListResponse
from core.types import JsonObject, require_json_object

logger = get_logger(__name__)
T = TypeVar("T", bound=BaseModel)


class CRUDRouterGenerator(Generic[T]):
    """
    Генератор роутеров для репозиториев.

    Автоматически создает стандартные эндпоинты репозитория:
    - Стандартные CRUD (get, set, delete, list, get_many).
    """

    def __init__(
        self,
        repository: BaseRepository[T],
        prefix: str,
        tags: Sequence[str | Enum],
        repository_dependency: Callable[[], BaseRepository[T]],
    ) -> None:
        self._repository: BaseRepository[T] = repository
        self._prefix: str = prefix
        self._tags: list[str | Enum] = list(tags)
        self._repository_dependency: Callable[[], BaseRepository[T]] = repository_dependency
        self._model_class: type[T] = repository.model_class

    def generate_router(self) -> APIRouter:
        """Генерирует FastAPI роутер со стандартными CRUD эндпоинтами."""
        router = APIRouter(prefix=self._prefix, tags=self._tags)

        self._add_standard_crud(router)

        return router

    def _add_standard_crud(self, router: APIRouter) -> None:
        """Добавляет стандартные CRUD эндпоинты"""
        repository_dependency = self._repository_dependency

        async def list_entities(
            repository: Annotated[BaseRepository[T], Depends(repository_dependency)],
            limit: Annotated[int, Query(ge=1, le=1000)] = 100,
            offset: Annotated[int, Query(ge=0)] = 0,
        ) -> ListResponse[JsonObject]:
            """Получить страницу сущностей."""
            entities = await repository.list(limit=limit, offset=offset)
            return ListResponse[JsonObject](
                items=[
                    require_json_object(entity.model_dump(mode="json"), "crud.list.item")
                    for entity in entities
                ],
            )

        async def get_entity(
            entity_id: str,
            repository: Annotated[BaseRepository[T], Depends(repository_dependency)],
        ) -> JsonObject:
            """Получить сущность по ID"""
            entity = await repository.get(entity_id)
            if not entity:
                raise HTTPException(status_code=404, detail=f"Entity '{entity_id}' not found")
            return require_json_object(entity.model_dump(mode="json"), "crud.entity")

        async def create_or_update_entity(
            entity_data: JsonObject,
            repository: Annotated[BaseRepository[T], Depends(repository_dependency)],
        ) -> JsonObject:
            """Создать или обновить сущность"""
            try:
                entity = self._model_class.model_validate(entity_data)
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f"Invalid data: {exc}") from exc

            success = await repository.set(entity)
            if not success:
                raise HTTPException(status_code=500, detail="Failed to save")
            return require_json_object(entity.model_dump(mode="json"), "crud.entity")

        async def delete_entity(
            entity_id: str,
            repository: Annotated[BaseRepository[T], Depends(repository_dependency)],
        ) -> JsonObject:
            """Удалить сущность по ID"""
            success = await repository.delete(entity_id)
            if not success:
                raise HTTPException(status_code=404, detail=f"Entity '{entity_id}' not found")
            return {"success": True, "entity_id": entity_id}

        async def get_many_entities(
            entity_ids: list[str],
            repository: Annotated[BaseRepository[T], Depends(repository_dependency)],
        ) -> dict[str, JsonObject]:
            """Получить несколько сущностей по ID"""
            if not entity_ids:
                return {}
            entities = await repository.get_many(entity_ids)
            return {
                eid: require_json_object(entity.model_dump(mode="json"), f"crud.many.{eid}")
                for eid, entity in entities.items()
            }

        router.add_api_route(
            "",
            list_entities,
            methods=["GET"],
            response_model=ListResponse[JsonObject],
            summary="List entities",
        )
        router.add_api_route(
            "/{entity_id}",
            get_entity,
            methods=["GET"],
            response_model=JsonObject,
            summary="Get entity",
        )
        router.add_api_route(
            "",
            create_or_update_entity,
            methods=["POST"],
            response_model=JsonObject,
            summary="Create or update entity",
        )
        router.add_api_route(
            "/{entity_id}",
            delete_entity,
            methods=["DELETE"],
            response_model=JsonObject,
            summary="Delete entity",
        )
        router.add_api_route(
            "/many",
            get_many_entities,
            methods=["POST"],
            response_model=dict[str, JsonObject],
            summary="Get many entities",
        )
