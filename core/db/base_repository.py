"""
Базовый репозиторий для работы с моделями.
Чистая архитектура без компромиссов:
- НЕ наследуется от Storage (композиция)
- is_global определяет поведение (без ветвлений)
- Каждый репозиторий знает свою таблицу
"""

from abc import ABC, abstractmethod
from typing import Dict, Generic, List, Optional, Type, TypeVar

from core.context import get_context
from core.db.storage import Storage
from core.logging import get_logger

logger = get_logger(__name__)
T = TypeVar("T")


class BaseRepository(ABC, Generic[T]):
    """
    Базовый репозиторий для работы с моделями.

    Архитектура:
    - Композиция с Storage (приватный _storage)
    - is_global определяет изоляцию (атрибут класса)
    - owner_service определяет какому сервису принадлежит репозиторий
    - Каждый репозиторий знает свою таблицу (_get_table_name)

    Логика изоляции:
    - is_global=True → ключ: {prefix}:{id}
    - is_global=False → ключ: company:{company_id}:{prefix}:{id}

    Логика маршрутизации:
    - Если settings.server.name == owner_service → работа с БД напрямую
    - Иначе → HTTP запросы к сервису-владельцу
    """

    is_global: bool = False
    owner_service: str = "core"  # Сервис-владелец репозитория
    api_prefix: str = ""  # Префикс для HTTP API (без двоеточия)

    @classmethod
    def get_service_url(cls) -> str:
        """
        Возвращает URL сервиса-владельца репозитория.
        Переопределяется в каждом репозитории для указания своего контейнера.
        """
        raise NotImplementedError(
            f"Репозиторий {cls.__name__} должен реализовать get_service_url() для работы через HTTP"
        )

    def __init__(self, storage: Storage, model_class: Type[T]):
        """
        Args:
            storage: Экземпляр Storage для работы с БД
            model_class: Класс Pydantic модели
        """
        self._storage = storage
        self.model_class = model_class

    def _get_key(self, entity_id: str) -> str:
        """
        Формирует базовый ключ для хранения сущности.

        Дефолтная реализация для обратной совместимости.
        Переопределите если нужна кастомная логика.

        Args:
            entity_id: Идентификатор сущности

        Returns:
            Базовый ключ (entity_id как есть)
        """
        return entity_id

    def _get_prefix(self) -> str:
        """
        Возвращает префикс для поиска сущностей.

        Дефолтная реализация для обратной совместимости.
        Переопределите если нужна кастомная логика.

        Returns:
            Пустой префикс
        """
        return ""

    def _get_table_name(self) -> str:
        """
        Возвращает имя таблицы БД для этого репозитория.

        Returns:
            Имя таблицы
        """
        return "storage"

    def _get_table(self) -> str:
        """
        Алиас для _get_table_name() для обратной совместимости.

        Returns:
            Имя таблицы
        """
        return self._get_table_name()

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
        - is_global=False → добавляет префикс company:{subdomain}:

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

        # Используем subdomain если есть, иначе fallback на company_id
        company_identifier = context.active_company.subdomain or context.active_company.company_id
        return f"company:{company_identifier}:{key}"

    def _build_final_prefix(self) -> Optional[str]:
        """
        Формирует финальный префикс для фильтрации с учетом изоляции.

        Используется для SQL LIKE запросов.

        Returns:
            Префикс с компанией или None если is_global=True
        """
        if self.is_global:
            return None

        context = get_context()
        if not context or not context.active_company:
            return None

        # Используем subdomain если есть, иначе fallback на company_id
        company_identifier = context.active_company.subdomain or context.active_company.company_id
        prefix = self._get_prefix()
        return f"company:{company_identifier}:{prefix}"

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

        data = await self._storage.get_with_session_and_table(final_key, table_name)
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
        return await self._storage.set_with_table(final_key, data, table_name)

    async def delete(self, entity_id: str) -> bool:
        """
        Удаляет сущность по ID.

        Args:
            entity_id: Идентификатор

        Returns:
            True если удалено
        """
        base_key = self._get_key(entity_id)
        final_key = self._build_final_key(base_key)
        table_name = self._get_table_name()
        return await self._storage.delete_with_table(final_key, table_name)

    async def list(self, *, limit: int, offset: int = 0) -> list[T]:
        """
        Возвращает страницу сущностей.

        Args:
            limit: Максимальное количество результатов (обязательный)
            offset: Смещение для пагинации
        """
        base_prefix = self._get_prefix()
        final_prefix = self._build_final_key(base_prefix)
        table_name = self._get_table_name()

        all_data = await self._storage.get_all_by_prefix_and_table(
            final_prefix, table_name, limit, offset
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

    async def count_all(self) -> int:
        """Количество всех сущностей компании в таблице."""
        base_prefix = self._get_prefix()
        final_prefix = self._build_final_key(base_prefix)
        table_name = self._get_table_name()
        return await self._storage._count_by_prefix_and_table(final_prefix, table_name)

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

        all_data = await self._storage.get_many_with_table(final_keys, table_name)

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
