"""Health микросервисов для публичной витрины статуса (`GET /frontend/api/services/status`, anonymous)."""

from __future__ import annotations

import asyncio
import time

import httpx2

from apps.frontend.models import ServiceHealthTarget, ServiceStatus
from core.clients.service_client import ServiceClient, ServiceClientError
from core.logging import get_logger
from core.pagination import OffsetPage

logger = get_logger(__name__)

SERVICE_HEALTH_TARGETS: tuple[ServiceHealthTarget, ...] = (
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
    httpx2.ConnectError,
    httpx2.TimeoutException,
    httpx2.HTTPStatusError,
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


async def _check_service(service_client: ServiceClient, target: ServiceHealthTarget) -> ServiceStatus:
    started = time.time()
    _ = await service_client.get(target.name, target.health_url)
    return ServiceStatus(
        name=target.name,
        status="healthy",
        url=_service_status_display_url(target.name),
        response_time=round((time.time() - started) * 1000, 2),
    )


async def collect_services_status(service_client: ServiceClient, *, limit: int, offset: int) -> OffsetPage[ServiceStatus]:
    results = await asyncio.gather(
        *(_check_service(service_client, target) for target in SERVICE_HEALTH_TARGETS),
        return_exceptions=True,
    )
    statuses: list[ServiceStatus] = []
    for target, result in zip(SERVICE_HEALTH_TARGETS, results, strict=True):
        if isinstance(result, ServiceStatus):
            statuses.append(result)
        elif isinstance(result, _NETWORK_ERRORS):
            logger.warning("services.status.unavailable", service=target.name, error=str(result))
            statuses.append(
                ServiceStatus(
                    name=target.name,
                    status="unhealthy",
                    url=_service_status_display_url(target.name),
                    response_time=None,
                )
            )
        else:
            raise result
    return OffsetPage[ServiceStatus](
        items=statuses[offset : offset + limit], total=len(statuses), limit=limit, offset=offset
    )
