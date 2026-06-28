"""
API для проверки статуса микросервисов
"""
import asyncio
import time
from typing import Annotated

import httpx
from fastapi import APIRouter, Query

from apps.frontend.dependencies import ContainerDep
from apps.frontend.models import ServiceHealthTarget, ServiceStatus
from core.clients.service_client import ServiceClient, ServiceClientError
from core.logging import get_logger
from core.pagination import OffsetPage

logger = get_logger(__name__)
router = APIRouter(prefix="/api/services", tags=["services"])

SERVICES: tuple[ServiceHealthTarget, ...] = (
    ServiceHealthTarget(name="flows", health_url="/flows/api/v1/health"),
    ServiceHealthTarget(name="crm", health_url="/crm/api/v1/health"),
    ServiceHealthTarget(name="rag", health_url="/rag/api/health"),
    ServiceHealthTarget(name="sync", health_url="/sync/api/health"),
    ServiceHealthTarget(name="worktracker", health_url="/worktracker/health"),
    ServiceHealthTarget(name="secrets", health_url="/secrets/health"),
    ServiceHealthTarget(name="office", health_url="/documents/api/health"),
    ServiceHealthTarget(name="provider_litserve", health_url="/litserve/health"),
)

_NETWORK_ERRORS = (
    httpx.ConnectError,
    httpx.TimeoutException,
    httpx.HTTPStatusError,
    ConnectionError,
    OSError,
    ServiceClientError,
)

def _service_status_display_url(name: str) -> str:
    if name == "flows":
        return "/flows"
    if name == "provider_litserve":
        return "/litserve"
    return f"/{name}"

async def _check_service(service_client: ServiceClient, name: str, health_url: str) -> ServiceStatus:
    display_url = _service_status_display_url(name)
    start = time.time()
    _ = await service_client.get(name, health_url)
    elapsed_ms = (time.time() - start) * 1000
    return ServiceStatus(
        name=name,
        status="healthy",
        url=display_url,
        response_time=round(elapsed_ms, 2),
    )

@router.get("/status", response_model=OffsetPage[ServiceStatus])
async def get_services_status(
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[ServiceStatus]:
    service_client = container.service_client

    tasks = [
        _check_service(service_client, service.name, service.health_url)
        for service in SERVICES
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    statuses: list[ServiceStatus] = []
    for service, result in zip(SERVICES, results):
        if isinstance(result, ServiceStatus):
            statuses.append(result)
        elif isinstance(result, _NETWORK_ERRORS):
            logger.warning("Сервис %s недоступен: %s", service.name, result)
            display_url = _service_status_display_url(service.name)
            statuses.append(
                ServiceStatus(
                    name=service.name,
                    status="unhealthy",
                    url=display_url,
                    response_time=None,
                )
            )
        else:
            raise result

    page = statuses[offset:offset + limit]
    return OffsetPage[ServiceStatus](items=page, total=len(statuses), limit=limit, offset=offset)
