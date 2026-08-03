"""HTTP client for capability-gateway API on top of ServiceClient."""

from __future__ import annotations

from core.capabilities import CapabilityDocumentation, CapabilityLanguage
from core.clients.service_client import ServiceClient

_DOCUMENTATION_PATH = "/capability-gateway/api/v1/capabilities/documentation"


class CapabilityGatewayClient:
    """REST client for capability-gateway documentation and related reads."""

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
