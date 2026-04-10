"""
API для проверки статуса микросервисов
"""
import asyncio
import logging
import time
from typing import List

import httpx
from fastapi import APIRouter

from apps.frontend.dependencies import ContainerDep
from apps.frontend.models import ServiceStatus
from core.clients.service_client import ServiceClientError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/services", tags=["services"])

SERVICES = [
    {"name": "flows", "url": "/flows/api/v1/health"},
    {"name": "crm", "url": "/crm/api/v1/health"},
    {"name": "rag", "url": "/rag/api/health"},
    {"name": "sync", "url": "/sync/api/health"},
    {"name": "office", "url": "/documents/api/health"},
]

_NETWORK_ERRORS = (
    httpx.ConnectError,
    httpx.TimeoutException,
    httpx.HTTPStatusError,
    ConnectionError,
    OSError,
    ServiceClientError,
)


async def _check_service(service_client: object, name: str, health_url: str) -> ServiceStatus:
    display_url = "/flows" if name == "flows" else f"/{name}"
    start = time.time()
    await service_client.get(name, health_url)
    elapsed_ms = (time.time() - start) * 1000
    return ServiceStatus(
        name=name,
        status="healthy",
        url=display_url,
        response_time=round(elapsed_ms, 2),
    )


@router.get("/status", response_model=List[ServiceStatus])
async def get_services_status(container: ContainerDep):
    service_client = container.service_client

    tasks = [
        _check_service(service_client, svc["name"], svc["url"])
        for svc in SERVICES
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    statuses: list[ServiceStatus] = []
    for svc, result in zip(SERVICES, results):
        if isinstance(result, ServiceStatus):
            statuses.append(result)
        elif isinstance(result, _NETWORK_ERRORS):
            logger.warning("Сервис %s недоступен: %s", svc["name"], result)
            display_url = "/flows" if svc["name"] == "flows" else f"/{svc['name']}"
            statuses.append(ServiceStatus(
                name=svc["name"],
                status="unhealthy",
                url=display_url,
                response_time=None,
            ))
        else:
            raise result

    return statuses
