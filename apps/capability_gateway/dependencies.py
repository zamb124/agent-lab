"""FastAPI dependencies для capability-gateway."""

from typing import Annotated

from fastapi import Depends

from apps.capability_gateway.container import (
    CapabilityGatewayContainer,
    get_capability_gateway_container,
)


def get_container() -> CapabilityGatewayContainer:
    return get_capability_gateway_container()


ContainerDep = Annotated[CapabilityGatewayContainer, Depends(get_container)]
