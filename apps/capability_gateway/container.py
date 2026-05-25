"""DI контейнер capability-gateway."""

from __future__ import annotations

from typing import cast

from apps.capability_gateway.config import get_capability_gateway_settings
from apps.capability_gateway.services.context_service import CapabilityContextService
from apps.capability_gateway.services.contracts import CapabilityGatewayContainerProtocol
from apps.capability_gateway.services.registry import CapabilityRegistry
from core.clients.redis_client import RedisClient
from core.clients.service_client import ServiceClient
from core.container import BaseContainer, ContainerRegistry, lazy
from core.logging import get_logger
from core.text_transforms import TextTransformService

logger = get_logger(__name__)


class CapabilityGatewayContainer(BaseContainer):
    """Composition root trusted capability gateway."""

    @lazy
    def capability_context_service(self) -> CapabilityContextService:
        return CapabilityContextService(
            container=cast(CapabilityGatewayContainerProtocol, cast(object, self))
        )

    @lazy
    def text_transform_service(self) -> TextTransformService:
        return TextTransformService()

    @lazy
    def service_client(self) -> ServiceClient:
        return ServiceClient()

    @lazy
    def redis_client(self) -> RedisClient:
        settings = get_capability_gateway_settings()
        return RedisClient(settings.database.redis_url)

    @lazy
    def capability_registry(self) -> CapabilityRegistry:
        return CapabilityRegistry(
            container=cast(CapabilityGatewayContainerProtocol, cast(object, self)),
            context_service=self.capability_context_service,
            text_transform_service=self.text_transform_service,
        )


def _create_capability_gateway_container() -> CapabilityGatewayContainer:
    settings = get_capability_gateway_settings()
    if not settings.database.shared_url:
        raise ValueError("database.shared_url is required для capability-gateway")
    return CapabilityGatewayContainer(
        db_url=settings.database.shared_url,
        shared_db_url=settings.database.shared_url,
    )


_capability_gateway_registry: ContainerRegistry[CapabilityGatewayContainer] = ContainerRegistry(
    _create_capability_gateway_container, name="CapabilityGatewayContainer"
)

get_capability_gateway_container = _capability_gateway_registry.get
reset_capability_gateway_container = _capability_gateway_registry.reset
