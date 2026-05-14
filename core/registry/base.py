"""
Базовый интерфейс Resource Registry.

Универсальный реестр для регистрации и получения ресурсов платформы.
Zero-Guess: все ресурсы регистрируются явно при startup.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Generic, List, TypeVar

from core.errors import ResourceAlreadyExistsError, ResourceNotFoundError

T = TypeVar("T")


class ResourceRegistry(ABC, Generic[T]):
    """
    Универсальный реестр ресурсов.

    Zero-Guess принципы:
    1. Все ресурсы регистрируются явно (при startup или через API)
    2. Попытка зарегистрировать дубликат = ошибка
    3. Попытка получить несуществующий ресурс = ошибка
    4. Никаких fallback значений

    Examples:
        >>> registry = NodeRegistry()
        >>> registry.register("llm_node", LlmNode)
        >>> node_class = registry.get("llm_node")
    """

    def __init__(self):
        self._resources: Dict[str, T] = {}
        self._metadata: Dict[str, Dict[str, Any]] = {}

    @abstractmethod
    def register(self, key: str, resource: T, metadata: Dict[str, Any] = None) -> None:
        """
        Регистрирует ресурс в реестре.

        Args:
            key: Уникальный ключ ресурса
            resource: Ресурс для регистрации
            metadata: Дополнительные метаданные (опционально)

        Raises:
            ResourceAlreadyExistsError: Если ресурс уже зарегистрирован
        """
        if key in self._resources:
            raise ResourceAlreadyExistsError(
                resource_type=self.__class__.__name__,
                resource_id=key,
            )

        self._resources[key] = resource
        if metadata:
            self._metadata[key] = metadata

    @abstractmethod
    def get(self, key: str) -> T:
        """
        Получает ресурс из реестра.

        Args:
            key: Ключ ресурса

        Returns:
            Ресурс

        Raises:
            ResourceNotFoundError: Если ресурс не найден
        """
        if key not in self._resources:
            raise ResourceNotFoundError(
                resource_type=self.__class__.__name__,
                resource_id=key,
            )
        return self._resources[key]

    def has(self, key: str) -> bool:
        """
        Проверяет наличие ресурса в реестре.

        Args:
            key: Ключ ресурса

        Returns:
            True если ресурс существует
        """
        return key in self._resources

    def list_all(self) -> Dict[str, T]:
        """
        Возвращает все зарегистрированные ресурсы.

        Returns:
            Dict[key, resource]
        """
        return dict(self._resources)

    def list_keys(self) -> List[str]:
        """
        Возвращает список всех ключей.

        Returns:
            Список ключей ресурсов
        """
        return list(self._resources.keys())

    def get_metadata(self, key: str) -> Dict[str, Any]:
        """
        Получает метаданные ресурса.

        Args:
            key: Ключ ресурса

        Returns:
            Метаданные или пустой dict
        """
        return self._metadata.get(key, {})

    def unregister(self, key: str) -> None:
        """
        Удаляет ресурс из реестра.

        Args:
            key: Ключ ресурса

        Raises:
            ResourceNotFoundError: Если ресурс не найден
        """
        if key not in self._resources:
            raise ResourceNotFoundError(
                resource_type=self.__class__.__name__,
                resource_id=key,
            )
        del self._resources[key]
        if key in self._metadata:
            del self._metadata[key]

    def clear(self) -> None:
        """Очищает весь реестр (для тестов)."""
        self._resources.clear()
        self._metadata.clear()

    def count(self) -> int:
        """Возвращает количество зарегистрированных ресурсов."""
        return len(self._resources)


__all__ = ["ResourceRegistry"]
