"""DI процесса capability_gateway: trusted gateway sandbox capabilities."""

from typing import Annotated

from apps.capability_gateway.services.registry import CapabilityRegistry
from core.di import ServiceDi, http_di, task_di
from core.di.platform import files_service, redis_client


class CapabilityGatewayDi(ServiceDi, recipes=(redis_client, files_service)):
    capability_registry: CapabilityRegistry


Di = Annotated[CapabilityGatewayDi, http_di(CapabilityGatewayDi), task_di(CapabilityGatewayDi)]
