"""HTTP client for capability-gateway API on top of ServiceClient."""

from __future__ import annotations

from core.capabilities import (
    CapabilityCallRequest,
    CapabilityCallResponse,
    CapabilityDocumentation,
    CapabilityLanguage,
)
from core.clients.service_client import ServiceClient
from core.types import require_json_object

_DOCUMENTATION_PATH = "/capability-gateway/api/v1/capabilities/documentation"
_CALL_PATH = "/capability-gateway/api/v1/capabilities/call"


class CapabilityGatewayClient:
    """REST client for capability-gateway documentation and capability calls."""

    def __init__(self, service_client: ServiceClient | None = None) -> None:
        self._http: ServiceClient = (
            service_client if service_client is not None else ServiceClient()
        )

    async def get_documentation(self, language: CapabilityLanguage) -> CapabilityDocumentation:
        raw = await self._http.get(
            "capability_gateway",
            _DOCUMENTATION_PATH,
            params={"language": language},
            timeout=30.0,
        )
        if not isinstance(raw, dict):
            raise RuntimeError("capability documentation response must be an object")
        return CapabilityDocumentation.model_validate(raw)

    async def call(
        self,
        request: CapabilityCallRequest,
        *,
        timeout: float,
    ) -> CapabilityCallResponse:
        """POST /capabilities/call; status != ok — RuntimeError."""
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        raw = await self._http.post(
            "capability_gateway",
            _CALL_PATH,
            json=require_json_object(
                request.model_dump(mode="json"),
                "CapabilityCallRequest",
            ),
            timeout=timeout,
        )
        response = CapabilityCallResponse.model_validate(raw)
        if response.status != "ok":
            raise RuntimeError(
                f"capability call {request.name!r} status={response.status!r}"
            )
        return response
