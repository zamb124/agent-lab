"""
Базовый интерфейс Resource Registry.

Универсальный реестр для регистрации и получения ресурсов платформы.
Zero-Guess: все ресурсы регистрируются явно при startup.
"""

from typing import Generic, TypeVar

from core.errors import ResourceAlreadyExistsError, ResourceNotFoundError
from core.types import JsonObject

T = TypeVar("T")


class ResourceRegistry(Generic[T]):
    """
    Универсальный реестр ресурсов.

    Zero-Guess принципы:
    1. Все ресурсы регистрируются явно (при startup или через API)
    2. Попытка зарегистрировать дубликат = ошибка
    3. Попытка получить несуществующий ресурс = ошибка
    4. Никаких неявных значений

    Примеры:
        >>> registry = NodeRegistry()
        >>> registry.register("llm_node", LlmNode)
        >>> node_class = registry.get("llm_node")
    """

    def __init__(self) -> None:
        self._resources: dict[str, T] = {}
        self._metadata: dict[str, JsonObject] = {}

    def register(self, key: str, resource: T, metadata: JsonObject | None = None) -> None:
        """
        Регистрирует ресурс в реестре.

        Аргументы:
            key: Уникальный ключ ресурса
            resource: Ресурс для регистрации
            metadata: Дополнительные метаданные (опционально)

        Исключения:
            ResourceAlreadyExistsError: Если ресурс уже зарегистрирован
        """
        if key in self._resources:
            raise ResourceAlreadyExistsError(
                resource_type=self.__class__.__name__,
                resource_id=key,
            )

        self._resources[key] = resource
        if metadata is not None:
            self._metadata[key] = dict(metadata)

    def get(self, key: str) -> T:
        """
        Получает ресурс из реестра.

        Аргументы:
            key: Ключ ресурса

        Возвращает:
            Ресурс

        Исключения:
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

        Аргументы:
            key: Ключ ресурса

        Возвращает:
            True если ресурс существует
        """
        return key in self._resources

    def list_all(self) -> dict[str, T]:
        """
        Возвращает все зарегистрированные ресурсы.

        Возвращает:
            Словарь {key: resource}
        """
        return dict(self._resources)

    def list_keys(self) -> list[str]:
        """
        Возвращает список всех ключей.

        Возвращает:
            Список ключей ресурсов
        """
        return list(self._resources.keys())

    def get_metadata(self, key: str) -> JsonObject:
        """
        Получает метаданные ресурса.

        Аргументы:
            key: Ключ ресурса

        Возвращает:
            Метаданные или пустой dict
        """
        if key not in self._resources:
            raise ResourceNotFoundError(
                resource_type=self.__class__.__name__,
                resource_id=key,
            )
        metadata = self._metadata.get(key)
        if metadata is None:
            return {}
        return dict(metadata)

    def unregister(self, key: str) -> None:
        """
        Удаляет ресурс из реестра.

        Аргументы:
            key: Ключ ресурса

        Исключения:
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
