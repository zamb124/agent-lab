"""
Единый фасад работы с переменными компании.

`VariablesService` живёт в core и является единственной точкой доступа к переменным:
- хранение/CRUD делегируется secrets-сервису через `SecretsClient` (значения секретов
  шифруются и резолвятся лениво);
- резолвинг (scoped overrides + expression + зависимости `@var:`) выполняет
  `ResolutionEngine` на стороне потребителя по контексту исполнителя.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import overload

from core.clients.secrets_client import SecretsClient
from core.context import get_context
from core.logging import get_logger
from core.secrets.models import VariableResolveRequest, VariableWriteRequest
from core.types import JsonArray, JsonObject, JsonValue
from core.variables.engine import ResolutionEngine
from core.variables.models import (
    PlatformVariable,
    ResolutionContext,
    VariableValueKind,
    VariableValuePayload,
    VariableValueSpec,
)
from core.variables.resolver import VarResolver

logger = get_logger(__name__)


class VariablesService:
    """Фасад переменных компании поверх secrets-сервиса и движка резолвинга."""

    def __init__(self, secrets_client: SecretsClient):
        self._secrets_client: SecretsClient = secrets_client

    @staticmethod
    def _resolution_context() -> ResolutionContext:
        context = get_context()
        if context is None or context.active_company is None:
            raise RuntimeError(
                "VariablesService: требуется контекст запроса с активной компанией"
            )
        return ResolutionContext(
            company_id=context.active_company.company_id,
            user_id=context.user.user_id,
            namespace=context.active_namespace,
            channel=context.channel,
        )

    async def resolvable_definitions(
        self, context: ResolutionContext
    ) -> list[PlatformVariable]:
        """Определения переменных компании, доступные исполнителю (секреты — по access policy)."""
        response = await self._secrets_client.resolve_bundle(
            VariableResolveRequest(
                user_id=context.user_id,
                namespace=context.namespace,
                channel=context.channel,
            )
        )
        definitions: list[PlatformVariable] = []
        for item in response.items:
            if not item.resolvable or item.payload is None:
                continue
            definitions.append(
                PlatformVariable(
                    variable_key=item.variable_key,
                    company_id=context.company_id,
                    version=item.version,
                    payload=item.payload,
                    secret=item.secret,
                    shared_for_execution=item.shared_for_execution,
                    public=item.public,
                )
            )
        return definitions

    async def resolve_for_run(
        self,
        context: ResolutionContext,
        seed: Mapping[str, JsonValue] | None = None,
    ) -> dict[str, JsonValue]:
        """Материализует плоский map переменных компании для запуска (по контексту)."""
        definitions = await self.resolvable_definitions(context)
        return ResolutionEngine.resolve(definitions, context, seed)

    async def get_company_variables_map(self) -> dict[str, JsonValue]:
        """Резолвнутый map переменных компании для текущего контекста запроса."""
        context = self._resolution_context()
        return await self.resolve_for_run(context)

    @overload
    async def resolve(self, value: JsonObject) -> JsonObject: ...

    @overload
    async def resolve(self, value: JsonArray) -> JsonArray: ...

    @overload
    async def resolve(self, value: JsonValue) -> JsonValue: ...

    async def resolve(self, value: JsonValue) -> JsonValue:
        """Рекурсивно резолвит @var:key в значении по переменным компании."""
        variables_map = await self.get_company_variables_map()
        return VarResolver.resolve_deep(value, variables_map)

    async def set_var(
        self,
        key: str,
        value: JsonValue,
        is_secret: bool = False,
        groups: list[str] | None = None,
        description: str | None = None,
        *,
        shared_for_execution: bool = False,
        public: bool = False,
    ) -> PlatformVariable:
        """Создаёт/обновляет static-переменную компании (значение секрета шифруется)."""
        request = VariableWriteRequest(
            variable_key=key,
            payload=VariableValuePayload(
                base=VariableValueSpec(value_kind=VariableValueKind.STATIC, value=value)
            ),
            secret=is_secret,
            shared_for_execution=shared_for_execution,
            public=public,
            groups=groups or [],
            description=description or "",
        )
        return await self._secrets_client.upsert_variable(request)

    async def upsert(self, request: VariableWriteRequest) -> PlatformVariable:
        """Создаёт/обновляет переменную произвольной формы (scoped/expression)."""
        return await self._secrets_client.upsert_variable(request)

    async def get_var(self, key: str) -> PlatformVariable | None:
        """Возвращает переменную (значение секрета маскируется)."""
        return await self._secrets_client.get_variable(key)

    async def delete_var(self, key: str) -> bool:
        return await self._secrets_client.delete_variable(key)

    async def list_vars(self, *, limit: int = 1000, offset: int = 0) -> list[PlatformVariable]:
        """Список переменных компании (значения секретов маскируются)."""
        page = await self._secrets_client.list_variables(limit=limit, offset=offset)
        return page.items

    async def secret_variable_keys(self) -> list[str]:
        """Ключи секретных переменных компании (для аудита/маскирования; без значений)."""
        page = await self._secrets_client.list_variables(limit=1000, offset=0)
        return sorted(item.variable_key for item in page.items if item.secret)


__all__ = ["VariablesService"]
