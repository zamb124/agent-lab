"""Health микросервисов для публичной витрины статуса (`GET /frontend/api/services/status`, anonymous)."""

from __future__ import annotations

import asyncio
import json
import time

import httpx2

from apps.frontend.models import ServiceStatus
from core.clients.service_client import ServiceClient, ServiceClientError
from core.logging import get_logger
from core.pagination import OffsetPage

logger = get_logger(__name__)

SERVICE_HEALTH_TARGETS: tuple[str, ...] = (
    "flows",
    "crm",
    "rag",
    "sync",
    "worktracker",
    "secrets",
    "office",
    "provider_litserve",
)
_NETWORK_ERRORS = (
    httpx2.ConnectError,
    httpx2.TimeoutException,
    httpx2.HTTPStatusError,
    ConnectionError,
    OSError,
    ServiceClientError,
    json.JSONDecodeError,
)


def _service_status_display_url(name: str) -> str:
    if name == "provider_litserve":
        return "/litserve"
    return f"/{name}"


async def _check_service(service_client: ServiceClient, name: str) -> ServiceStatus:
    started = time.time()
    _ = await service_client.get(name, f"/{name}/health")
    return ServiceStatus(
        name=name,
        status="healthy",
        url=_service_status_display_url(name),
        response_time=round((time.time() - started) * 1000, 2),
    )


async def collect_services_status(service_client: ServiceClient, *, limit: int, offset: int) -> OffsetPage[ServiceStatus]:
    results = await asyncio.gather(
        *(_check_service(service_client, name) for name in SERVICE_HEALTH_TARGETS),
        return_exceptions=True,
    )
    statuses: list[ServiceStatus] = []
    for name, result in zip(SERVICE_HEALTH_TARGETS, results, strict=True):
        if isinstance(result, ServiceStatus):
            statuses.append(result)
        elif isinstance(result, _NETWORK_ERRORS):
            logger.warning("services.status.unavailable", service=name, error=str(result))
            statuses.append(
                ServiceStatus(
                    name=name,
                    status="unhealthy",
                    url=_service_status_display_url(name),
                    response_time=None,
                )
            )
        else:
            raise result
    return OffsetPage[ServiceStatus](
        items=statuses[offset : offset + limit], total=len(statuses), limit=limit, offset=offset
    )
