"""Типизированный клиент микросервиса secrets."""

from __future__ import annotations

from core.clients.service_client import ServiceClient
from core.pagination import OffsetPage
from core.secrets.models import (
    VariableResolveRequest,
    VariableResolveResponse,
    VariableWriteRequest,
)
from core.variables.models import PlatformVariable

_API_PREFIX = "/secrets/api/v1"


class SecretsClient:
    """Доступ к версионируемым переменным и секретам через secrets-сервис."""

    def __init__(self, service_client: ServiceClient | None = None) -> None:
        self._service_client: ServiceClient = (
            service_client if service_client is not None else ServiceClient()
        )

    async def upsert_variable(self, request: VariableWriteRequest) -> PlatformVariable:
        response = await self._service_client.post(
            "secrets",
            f"{_API_PREFIX}/variables",
            json=request.model_dump(mode="json"),
        )
        return PlatformVariable.model_validate(response)

    async def get_variable(self, variable_key: str) -> PlatformVariable | None:
        response = await self._service_client.get(
            "secrets",
            f"{_API_PREFIX}/variables/{variable_key}",
        )
        if response is None:
            return None
        return PlatformVariable.model_validate(response)

    async def list_variables(
        self, *, limit: int = 1000, offset: int = 0
    ) -> OffsetPage[PlatformVariable]:
        response = await self._service_client.get(
            "secrets",
            f"{_API_PREFIX}/variables",
            params={"limit": limit, "offset": offset},
        )
        return OffsetPage[PlatformVariable].model_validate(response)

    async def delete_variable(self, variable_key: str) -> bool:
        response = await self._service_client.delete(
            "secrets",
            f"{_API_PREFIX}/variables/{variable_key}",
        )
        if not isinstance(response, dict):
            return False
        return response.get("status") == "deleted"

    async def resolve_bundle(self, request: VariableResolveRequest) -> VariableResolveResponse:
        response = await self._service_client.post(
            "secrets",
            f"{_API_PREFIX}/variables/resolve",
            json=request.model_dump(mode="json"),
        )
        return VariableResolveResponse.model_validate(response)


__all__ = ["SecretsClient"]
