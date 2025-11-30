"""
Репозиторий для работы с stores (session store data).
Использует service БД, is_global=False (изолирован по компаниям).
"""

import json
import logging
from typing import Dict, Any, Optional, Set
from datetime import datetime, timezone
from sqlalchemy import text

from core.db.base_repository import BaseRepository
from core.db.storage import Storage

logger = logging.getLogger(__name__)


def serialize_store_data(data: Any, visited: Optional[Set[int]] = None) -> Any:
    """
    Сериализует данные store, обрабатывая циклические ссылки и несериализуемые объекты.
    """
    if visited is None:
        visited = set()
    
    if isinstance(data, (str, int, float, bool, type(None))):
        return data
    
    obj_id = id(data)
    if obj_id in visited:
        return None
    
    if isinstance(data, dict):
        visited.add(obj_id)
        result = {}
        for k, v in data.items():
            if not isinstance(k, (str, int, float, bool)):
                continue
            serialized_v = serialize_store_data(v, visited)
            if serialized_v is not None:
                result[k] = serialized_v
        visited.remove(obj_id)
        return result
    elif isinstance(data, (list, tuple)):
        visited.add(obj_id)
        result = []
        for item in data:
            serialized_item = serialize_store_data(item, visited)
            if serialized_item is not None:
                result.append(serialized_item)
        visited.remove(obj_id)
        return result
    else:
        try:
            str_repr = str(data)
            if len(str_repr) > 1000:
                return str_repr[:1000] + "..."
            return str_repr
        except Exception:
            return str(data)


class StoreRepository(BaseRepository[Dict[str, Any]]):
    """
    Репозиторий для работы с stores.
    is_global=False - stores изолированы по компаниям.
    owner_service=agents - принадлежит сервису agents.
    """
    
    is_global = False
    owner_service = "agents"
    api_prefix = "store"
    
    @classmethod
    def get_service_url(cls) -> str:
        """URL сервиса agents"""
        from apps.agents.db.repositories import get_agents_service_url
        return get_agents_service_url()

    def __init__(self, storage: Storage):
        # Используем dict как модель, так как store_data - это просто JSONB
        super().__init__(storage=storage, model_class=dict)

    def _get_key(self, store_id: str) -> str:
        return f"store:{store_id}"

    def _get_prefix(self) -> str:
        return "store:"

    def _get_table_name(self) -> str:
        return "stores"

    def _extract_entity_id(self, entity: Dict[str, Any]) -> str:
        # Для store entity - это сам store_id, который передается в методах
        raise NotImplementedError("StoreRepository не использует _extract_entity_id")

    async def get(self, store_id: str) -> Optional[Dict[str, Any]]:
        """Получить store по ID"""
        async with self._storage._get_session() as session:
            result = await session.execute(
                text("SELECT store_data FROM stores WHERE store_id = :store_id"),
                {"store_id": store_id}
            )
            row = result.first()
            return row[0] if row and row[0] else None

    async def set(self, store_id: str, store_data: Dict[str, Any]) -> bool:
        """Сохранить store"""
        if not isinstance(store_data, dict):
            raise ValueError(f"store_data должен быть dict, получен {type(store_data)}")
        
        try:
            if store_data and len(store_data) > 0:
                serialized_data = serialize_store_data(store_data)
                if serialized_data is None or (isinstance(serialized_data, dict) and len(serialized_data) == 0 and len(store_data) > 0):
                    raise ValueError(
                        f"Не удалось сериализовать store_data: содержит циклические ссылки или несериализуемые объекты. "
                        f"Исходные ключи: {list(store_data.keys())}"
                    )
            else:
                serialized_data = store_data
            
            store_data_json = json.dumps(serialized_data, default=str, ensure_ascii=False)
        except ValueError as e:
            raise ValueError(f"Ошибка сериализации store (store_id={store_id}): {e}") from e
        except Exception as e:
            raise ValueError(f"Ошибка сериализации store (store_id={store_id}): {type(e).__name__}: {e}") from e
        async with self._storage._get_session() as session:
            async with session.begin():
                await session.execute(
                    text("""
                        INSERT INTO stores (store_id, store_data, updated_at)
                        VALUES (:store_id, CAST(:store_data AS JSONB), CURRENT_TIMESTAMP)
                        ON CONFLICT (store_id)
                        DO UPDATE SET store_data = CAST(:store_data AS JSONB), updated_at = CURRENT_TIMESTAMP
                    """),
                    {"store_id": store_id, "store_data": store_data_json}
                )
        return True

    async def delete(self, store_id: str) -> bool:
        """Удалить store"""
        async with self._storage._get_session() as session:
            async with session.begin():
                await session.execute(
                    text("DELETE FROM stores WHERE store_id = :store_id"),
                    {"store_id": store_id}
                )
        return True

