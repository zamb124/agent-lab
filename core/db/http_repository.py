"""
HTTP прокси для удаленных репозиториев.

Когда сервис обращается к репозиторию другого сервиса,
вместо прямого доступа к БД используются HTTP запросы к API.

ЛЮБОЙ метод репозитория автоматически проксируется через HTTP.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Generic, TypeAlias, TypeVar

import httpx
from pydantic import BaseModel

from core.context import get_context
from core.db.base_repository import BaseRepository
from core.http import get_httpx_client
from core.logging import get_logger
from core.types import (
    JsonObject,
    JsonValue,
    parse_json_value,
    require_json_array,
    require_json_object,
)

logger = get_logger(__name__)
T = TypeVar("T", bound=BaseModel)
QueryParams: TypeAlias = Mapping[str, str | int]
RepositoryProxyResult: TypeAlias = T | list[T] | JsonValue | None


class HTTPRepositoryProxy(Generic[T]):
    """
    HTTP прокси для репозитория другого сервиса.

    Динамически проксирует ВСЕ методы репозитория через HTTP.
    Использует __getattr__ для перехвата любых вызовов методов.
    """

    def __init__(
        self,
        repository_class: type[BaseRepository[T]],
        model_class: type[T],
    ) -> None:
        """
        Args:
            repository_class: Класс репозитория (для получения URL и prefix)
            model_class: Класс Pydantic модели
        """
        self.repository_class: type[BaseRepository[T]] = repository_class
        self.model_class: type[T] = model_class
        self.repository_prefix: str = repository_class.api_prefix
        self.owner_service: str = repository_class.owner_service

    def _get_base_url(self) -> str:
        """Формирует базовый URL для API запросов"""
        service_url = self.repository_class.get_service_url()
        return f"{service_url}/{self.owner_service}/api/v1/{self.repository_prefix}"

    async def _request(
        self,
        method: str,
        path: str = "",
        *,
        headers: Mapping[str, str] | None = None,
        json_payload: JsonValue | None = None,
        params: QueryParams | None = None,
    ) -> JsonValue | None:
        """
        Выполняет HTTP запрос к API сервиса-владельца.
        Передает контекст (trace_id, company_id, user_id) в заголовках.
        """
        context = get_context()
        request_headers: dict[str, str] = dict(headers or {})

        if context:
            if context.trace_id:
                request_headers["X-Trace-Id"] = context.trace_id
            if context.auth_token:
                request_headers["Authorization"] = f"Bearer {context.auth_token}"
            if context.active_company:
                request_headers["X-Company-Id"] = context.active_company.company_id
            request_headers["X-User-Id"] = context.user.user_id

        url = f"{self._get_base_url()}{path}"

        logger.info(
            "HTTPRepositoryProxy request: %s %s, trace_id=%s",
            method,
            url,
            request_headers.get("X-Trace-Id"),
        )

        async with get_httpx_client(timeout=30.0) as client:
            response = await client.request(
                method,
                url,
                headers=request_headers,
                json=json_payload,
                params=params,
            )
            _ = response.raise_for_status()

            if response.content:
                return parse_json_value(response.content, f"{method} {url}")
            return None

    def __getattr__(self, name: str) -> Callable[..., Awaitable[RepositoryProxyResult[T]]]:
        """
        Перехватывает вызовы любых методов и проксирует через HTTP.

        Соглашение:
        - Метод репозитория → POST /{method_name}
        - Аргументы передаются в JSON body
        - Результат десериализуется в model_class если это dict/list
        """
        if name.startswith('_'):
            raise AttributeError(f"'{type(self).__name__}' has no attribute '{name}'")

        async def proxy_method(*args: JsonValue, **kwargs: JsonValue) -> RepositoryProxyResult[T]:
            # Собираем все аргументы в payload
            payload: JsonObject = {
                "args": list(args),
                "kwargs": kwargs,
            }

            try:
                result = await self._request(
                    "POST",
                    f"/method/{name}",
                    json_payload=payload,
                )
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404:
                    message = (
                        f"Метод '{name}' не найден в репозитории "
                        + self.repository_class.__name__
                    )
                    raise AttributeError(message) from exc
                raise

            return self._deserialize_result(result)

        return proxy_method

    def _deserialize_entity(self, result: JsonValue, field_name: str) -> T:
        data = require_json_object(result, field_name)
        return self.model_class.model_validate(data)

    def _deserialize_result(self, result: JsonValue | None) -> RepositoryProxyResult[T]:
        """Десериализует результат в модель если возможно"""
        if result is None:
            return None

        if isinstance(result, Mapping):
            return self._deserialize_entity(result, "repository.result")

        if isinstance(result, list):
            values = require_json_array(result, "repository.result")
            return [
                self._deserialize_entity(item, "repository.result[]")
                for item in values
            ]

        return result

    # Стандартные методы для обратной совместимости (оптимизированные пути)

    async def get(self, entity_id: str) -> T | None:
        """GET /{entity_id}"""
        try:
            data = await self._request("GET", f"/{entity_id}")
            if data is None:
                return None
            return self._deserialize_entity(data, f"repository.{entity_id}")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise

    async def set(self, entity: T) -> bool:
        """POST /"""
        entity_data = require_json_object(entity.model_dump(mode="json"), "repository.entity")
        _ = await self._request("POST", "", json_payload=entity_data)
        return True

    async def delete(self, entity_id: str) -> bool:
        """DELETE /{entity_id}"""
        try:
            _ = await self._request("DELETE", f"/{entity_id}")
            return True
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return False
            raise

    async def list(self, *, limit: int, offset: int = 0) -> list[T]:
        """GET /?limit={limit}&offset={offset}"""
        data = await self._request("GET", "", params={"limit": limit, "offset": offset})
        if data is None:
            return []
        values = require_json_array(data, "repository.list")
        return [
            self._deserialize_entity(item, "repository.list[]")
            for item in values
        ]

    async def get_many(self, entity_ids: list[str]) -> dict[str, T]:
        """POST /many"""
        if not entity_ids:
            return {}
        data = await self._request("POST", "/many", json_payload=entity_ids)
        if data is None:
            return {}
        entities = require_json_object(data, "repository.many")
        return {
            entity_id: self._deserialize_entity(value, f"repository.many.{entity_id}")
            for entity_id, value in entities.items()
        }
