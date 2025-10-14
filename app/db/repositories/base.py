"""
Базовый репозиторий для работы с моделями через Storage.
"""

from typing import Generic, TypeVar, Optional, List
from abc import ABC, abstractmethod

from app.db.repositories.storage import Storage

T = TypeVar('T')


class BaseRepository(ABC, Generic[T]):
    """
    Базовый репозиторий для работы с моделями.
    Инкапсулирует логику работы с Storage для конкретного типа модели.
    
    Все наследники ОБЯЗАНЫ реализовать:
    - _get_key(): формирование ключа
    - _get_prefix(): префикс для поиска
    - get(): получение по ID
    - set(): сохранение
    - delete(): удаление
    
    Используется единообразный API как в Storage: get/set/delete
    """

    def __init__(self, storage: Storage = None):
        self.storage = storage or Storage()

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
        Получает сущность по ID.
        
        Args:
            entity_id: Идентификатор сущности
            
        Returns:
            Сущность или None если не найдена
        """
        pass

    @abstractmethod
    async def set(self, entity: T) -> bool:
        """
        Сохраняет сущность.
        
        Args:
            entity: Сущность для сохранения
            
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

