"""
Базовый репозиторий для работы с моделями через Storage.
Наследуется от Storage и добавляет типизированную работу с Pydantic моделями.
"""

import logging
from typing import Generic, TypeVar, Optional, List, Type, Any
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
        
        # Для TaskConfig используем безопасную сериализацию (избегаем циклических ссылок)
        if hasattr(entity, '__class__') and 'TaskConfig' in str(entity.__class__):
            import json
            # Получаем словарь, исключая context
            try:
                task_dict = entity.model_dump(exclude={'context'}, mode='python')
            except ValueError:
                # Если все еще есть циклические ссылки, используем более агрессивный подход
                task_dict = {}
                for field_name, field_value in entity.model_fields.items():
                    if field_name == 'context':
                        continue
                    try:
                        field_data = getattr(entity, field_name, None)
                        task_dict[field_name] = self._sanitize_for_json(field_data)
                    except Exception:
                        task_dict[field_name] = None
            
            # Санитизируем весь словарь рекурсивно
            sanitized_dict = self._sanitize_for_json(task_dict)
            data = json.dumps(sanitized_dict, default=str)
            set_kwargs = {'force_global': True}
        else:
            data = entity.model_dump_json()
            set_kwargs = {}

        # Объединяем с переданными kwargs
        set_kwargs.update(kwargs)

        # Используем Storage.set напрямую через super() чтобы избежать рекурсии
        return await super().set(key, data, **set_kwargs)
    
    def _sanitize_for_json(self, value: Any, _depth: int = 0, _seen: Optional[set] = None) -> Any:
        """Рекурсивно санитизирует значение для JSON сериализации, избегая циклических ссылок"""
        if _seen is None:
            _seen = set()
        
        if _depth > 10:  # Защита от бесконечной рекурсии
            return str(value)
        
        # Проверка на циклические ссылки
        obj_id = id(value)
        if obj_id in _seen:
            return f"<circular reference: {type(value).__name__}>"
        
        if value is None or isinstance(value, (bool, int, float, str)):
            return value
        
        # Для примитивных типов не добавляем в _seen
        if isinstance(value, (dict, list, tuple)) or (hasattr(value, '__dict__') and not isinstance(value, type)):
            _seen.add(obj_id)
        
        try:
            if isinstance(value, dict):
                result = {
                    str(k): self._sanitize_for_json(v, _depth + 1, _seen)
                    for k, v in value.items()
                }
                _seen.discard(obj_id)
                return result
            
            if isinstance(value, (list, tuple)):
                result = [self._sanitize_for_json(item, _depth + 1, _seen) for item in value]
                _seen.discard(obj_id)
                return result
            
            # Для объектов с model_dump используем его
            if hasattr(value, 'model_dump'):
                try:
                    # Исключаем проблемные поля
                    excluded = {'context', 'container', 'interface', '_state', '_context'}
                    dumped = value.model_dump(mode='python', exclude=excluded)
                    result = self._sanitize_for_json(dumped, _depth + 1, _seen)
                    _seen.discard(obj_id)
                    return result
                except Exception:
                    _seen.discard(obj_id)
                    return str(value)
            
            # Для объектов с __dict__ - извлекаем атрибуты
            if hasattr(value, '__dict__'):
                try:
                    obj_dict = {}
                    for key, val in value.__dict__.items():
                        if key.startswith('_') and key not in ('_state', '_context'):
                            continue
                        obj_dict[key] = self._sanitize_for_json(val, _depth + 1, _seen)
                    _seen.discard(obj_id)
                    return obj_dict
                except Exception:
                    _seen.discard(obj_id)
                    return str(value)
            
            # Для других объектов - конвертируем в строку
            _seen.discard(obj_id)
            return str(value)
        except Exception as e:
            _seen.discard(obj_id)
            return f"<error serializing {type(value).__name__}: {str(e)}>"

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

