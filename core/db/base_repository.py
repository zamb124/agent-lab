"""
Базовый репозиторий для работы с моделями.
Чистая архитектура без компромиссов:
- НЕ наследуется от Storage (композиция)
- is_global определяет поведение (без ветвлений)
- Каждый репозиторий знает свою таблицу
"""

import logging
import json
from typing import Generic, TypeVar, Optional, List, Dict, Type, Any
from abc import ABC, abstractmethod

from core.db.storage import Storage
from core.context import get_context

logger = logging.getLogger(__name__)

T = TypeVar('T')


class BaseRepository(ABC, Generic[T]):
    """
    Базовый репозиторий для работы с моделями.
    
    Архитектура:
    - Композиция с Storage (приватный _storage)
    - is_global определяет изоляцию (атрибут класса)
    - Каждый репозиторий знает свою таблицу (_get_table_name)
    
    Логика изоляции:
    - is_global=True → ключ: {prefix}:{id}
    - is_global=False → ключ: company:{company_id}:{prefix}:{id}
    """
    
    is_global: bool = False

    def __init__(self, storage: Storage, model_class: Type[T]):
        """
        Args:
            storage: Экземпляр Storage для работы с БД
            model_class: Класс Pydantic модели
        """
        self._storage = storage
        self.model_class = model_class

    @abstractmethod
    def _get_key(self, entity_id: str) -> str:
        """
        Формирует базовый ключ для хранения сущности.
        
        Args:
            entity_id: Идентификатор сущности
            
        Returns:
            Базовый ключ (например, "agent:agent_id")
        """
        pass

    @abstractmethod
    def _get_prefix(self) -> str:
        """
        Возвращает префикс для поиска сущностей.
        
        Returns:
            Префикс (например, "agent:")
        """
        pass

    @abstractmethod
    def _get_table_name(self) -> str:
        """
        Возвращает имя таблицы БД для этого репозитория.
        
        Returns:
            Имя таблицы (например, "storage", "users", "tasks")
        """
        pass

    @abstractmethod
    def _extract_entity_id(self, entity: T) -> str:
        """
        Извлекает ID из сущности.
        
        Args:
            entity: Сущность для извлечения ID
            
        Returns:
            ID сущности
        """
        pass

    def _build_final_key(self, key: str) -> str:
        """
        Формирует финальный ключ с учетом изоляции.
        
        Незыблемая логика без ветвлений:
        - is_global=True → возвращает ключ как есть
        - is_global=False → добавляет префикс company:{company_id}:
        
        Args:
            key: Базовый ключ
            
        Returns:
            Финальный ключ для хранения
        """
        if self.is_global:
            return key
        
        context = get_context()
        if not context or not context.active_company:
            raise ValueError(
                f"Репозиторий {self.__class__.__name__} требует активную компанию в контексте "
                f"(is_global=False)"
            )
        
        company_id = context.active_company.company_id
        return f"company:{company_id}:{key}"

    async def get(self, entity_id: str) -> Optional[T]:
        """
        Получает сущность по ID.
        
        Args:
            entity_id: Идентификатор сущности
            
        Returns:
            Сущность или None если не найдена
        """
        base_key = self._get_key(entity_id)
        final_key = self._build_final_key(base_key)
        table_name = self._get_table_name()
        
        data = await self._storage._get_with_session_and_table(final_key, table_name)
        if data is None:
            return None
        
        return self.model_class.model_validate_json(data)

    async def set(self, entity: T) -> bool:
        """
        Сохраняет сущность.
        
        Args:
            entity: Сущность для сохранения
            
        Returns:
            True если сохранение успешно
        """
        entity_id = self._extract_entity_id(entity)
        base_key = self._get_key(entity_id)
        final_key = self._build_final_key(base_key)
        table_name = self._get_table_name()
        
        data = entity.model_dump_json()
        return await self._storage._set_with_table(final_key, data, table_name)

    async def delete(self, entity_id: str) -> bool:
        """
        Удаляет сущность по ID.
        
        Args:
            entity_id: Идентификатор сущности
            
        Returns:
            True если удаление успешно
        """
        base_key = self._get_key(entity_id)
        final_key = self._build_final_key(base_key)
        table_name = self._get_table_name()
        
        return await self._storage._delete_with_table(final_key, table_name)

    async def list_all(self, limit: int = 100) -> List[T]:
        """
        Возвращает список всех сущностей.
        
        Args:
            limit: Максимальное количество результатов
            
        Returns:
            Список сущностей
        """
        base_prefix = self._get_prefix()
        final_prefix = self._build_final_key(base_prefix)
        table_name = self._get_table_name()
        
        all_data = await self._storage._get_all_by_prefix_and_table(
            final_prefix, table_name, limit
        )
        
        entities = []
        for key, data in all_data.items():
            try:
                entity = self.model_class.model_validate_json(data)
                entities.append(entity)
            except Exception as e:
                logger.error(f"Ошибка парсинга {key}: {e}")
                continue
        
        return entities

    async def get_many(self, entity_ids: List[str]) -> Dict[str, T]:
        """
        Получает несколько сущностей по списку ID.
        
        Args:
            entity_ids: Список идентификаторов
            
        Returns:
            Словарь {entity_id: entity}
        """
        if not entity_ids:
            return {}
        
        table_name = self._get_table_name()
        final_keys = [self._build_final_key(self._get_key(eid)) for eid in entity_ids]
        
        all_data = await self._storage._get_many_with_table(final_keys, table_name)
        
        result = {}
        for i, entity_id in enumerate(entity_ids):
            final_key = final_keys[i]
            if final_key in all_data:
                try:
                    entity = self.model_class.model_validate_json(all_data[final_key])
                    result[entity_id] = entity
                except Exception as e:
                    logger.error(f"Ошибка парсинга {entity_id}: {e}")
                    continue
        
        return result
