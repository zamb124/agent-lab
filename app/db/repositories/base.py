"""
Базовый репозиторий для работы с моделями через Storage.
Наследуется от Storage и добавляет типизированную работу с Pydantic моделями.
"""

import logging
from typing import Generic, TypeVar, Optional, List, Type
from abc import ABC, abstractmethod

from app.db.repositories.storage import Storage

logger = logging.getLogger(__name__)

T = TypeVar('T')


class BaseRepository(Storage, ABC, Generic[T]):
    """
    Базовый репозиторий для работы с моделями.
    Наследуется от Storage, поэтому имеет все его методы (get/set/delete).
    Добавляет типизированную работу с Pydantic моделями через Generic[T].

    Все наследники ОБЯЗАНЫ реализовать:
    - _get_key(): формирование ключа
    - _get_prefix(): префикс для поиска
    - get(): получение по ID (типизированное)
    - set(): сохранение (типизированное)
    - delete(): удаление

    Репозитории расширяют функциональность Storage, но сохраняют обратную совместимость.
    """

    def __init__(self, model_class: Type[T] = None, storage: Storage = None):
        """
        Args:
            model_class: Класс Pydantic модели (опционально для обратной совместимости)
            storage: Экземпляр Storage (опционально, будет создан если не передан)
        """
        # Инициализируем Storage
        if storage:
            # Если передан storage, копируем его состояние
            self.session_factory = storage.session_factory
            self._table_cache = storage._table_cache
            self._metadata = storage._metadata
        else:
            # Инициализируем как новый Storage
            super().__init__()

        self.model_class = model_class

    @property
    def storage(self) -> 'Storage':
        """
        Свойство для обратной совместимости.
        Теперь репозиторий сам является Storage, но для совместимости
        возвращаем себя.
        """
        return self

    @abstractmethod
    def _get_key(self, entity_id: str) -> str:
        """
        Формирует ключ для хранения сущности в Storage.

        Args:
            entity_id: Идентификатор сущности

        Returns:
            Полный ключ для Storage
        """
        pass

    @abstractmethod
    def _get_prefix(self) -> str:
        """
        Возвращает префикс для поиска сущностей.

        Returns:
            Префикс (например, "agent:", "flow:")
        """
        pass

    @abstractmethod
    async def get(self, entity_id: str) -> Optional[T]:
        """
        Получает сущность по ID с типизацией.

        Args:
            entity_id: Идентификатор сущности

        Returns:
            Сущность типа T или None если не найдена
        """
        pass

    @abstractmethod
    async def set(self, entity: T) -> bool:
        """
        Сохраняет сущность с типизацией.

        Args:
            entity: Сущность типа T для сохранения

        Returns:
            True если сохранение успешно
        """
        pass

    @abstractmethod
    async def delete(self, entity_id: str) -> bool:
        """
        Удаляет сущность по ID.

        Args:
            entity_id: Идентификатор сущности

        Returns:
            True если удаление успешно
        """
        pass

    # === Вспомогательные методы для типизированной работы с моделями ===

    async def _get_typed(self, entity_id: str, **kwargs) -> Optional[T]:
        """
        Вспомогательный метод для получения сущности с типизацией.

        Args:
            entity_id: Идентификатор сущности
            **kwargs: Дополнительные параметры

        Returns:
            Сущность типа T или None
        """
        if not self.model_class:
            raise ValueError("model_class не задан для типизированной работы")

        key = self._get_key(entity_id)

        # Проверяем специальные параметры для TaskConfig
        get_kwargs = {}
        prefix = self._get_prefix().rstrip(':')
        if prefix == 'task':
            # Task всегда использует глобальный scope
            get_kwargs['force_global'] = True

        # Объединяем с переданными kwargs
        get_kwargs.update(kwargs)

        # Используем Storage.get напрямую через super() чтобы избежать рекурсии
        data = await super().get(key, **get_kwargs)
        if data is None:
            return None

        try:
            return self.model_class.model_validate_json(data)
        except Exception as e:
            logger.error(f"Ошибка парсинга {entity_id}: {e}")
            return None

    async def _set_typed(self, entity: T, **kwargs) -> bool:
        """
        Вспомогательный метод для сохранения сущности с типизацией.

        Args:
            entity: Сущность для сохранения
            **kwargs: Дополнительные параметры (например, force_global для TaskRepository)

        Returns:
            True если сохранение успешно
        """
        if not self.model_class:
            raise ValueError("model_class не задан для типизированной работы")

        # Получаем ID из сущности
        # Разные модели имеют разные поля для ID
        prefix = self._get_prefix().rstrip(':')
        entity_id = None

        # Проверяем стандартные поля ID
        for id_field in ['id', f"{prefix}_id", 'server_id', 'flow_id', 'task_id', 'session_id', 'agent_id', 'tool_id']:
            if hasattr(entity, id_field):
                entity_id = getattr(entity, id_field)
                if entity_id is not None:
                    break

        if entity_id is None:
            raise ValueError(f"Не удалось определить ID сущности {entity} (prefix: {prefix})")

        key = self._get_key(entity_id)
        data = entity.model_dump_json()

        # Проверяем специальные параметры
        set_kwargs = {}
        if hasattr(entity, '__class__') and 'TaskConfig' in str(entity.__class__):
            # TaskConfig всегда использует глобальный scope
            set_kwargs['force_global'] = True

        # Объединяем с переданными kwargs
        set_kwargs.update(kwargs)

        # Используем Storage.set напрямую через super() чтобы избежать рекурсии
        return await super().set(key, data, **set_kwargs)

    async def _delete_typed(self, entity_id: str, **kwargs) -> bool:
        """
        Вспомогательный метод для удаления сущности.

        Args:
            entity_id: Идентификатор сущности
            **kwargs: Дополнительные параметры

        Returns:
            True если удаление успешно
        """
        key = self._get_key(entity_id)

        # Проверяем специальные параметры для TaskConfig
        delete_kwargs = {}
        prefix = self._get_prefix().rstrip(':')
        if prefix == 'task':
            # Task всегда использует глобальный scope
            delete_kwargs['force_global'] = True

        # Объединяем с переданными kwargs
        delete_kwargs.update(kwargs)

        # Используем Storage.delete напрямую через super() чтобы избежать рекурсии
        return await super().delete(key, **delete_kwargs)

    async def list_all_typed(self, limit: int = 100) -> List[T]:
        """
        Возвращает список всех сущностей с типизацией (оптимизировано).

        Args:
            limit: Максимальное количество результатов

        Returns:
            Список сущностей типа T
        """
        if not self.model_class:
            raise ValueError("model_class не задан для типизированной работы")

        prefix = self._get_prefix()
        # Используем оптимизированный метод из Storage
        all_data = await self.get_all_by_prefix(prefix, limit=limit)

        entities = []
        for key, data in all_data.items():
            try:
                entity = self.model_class.model_validate_json(data)
                entities.append(entity)
            except Exception as e:
                logger.error(f"Ошибка парсинга {key}: {e}")
                continue

        return entities

