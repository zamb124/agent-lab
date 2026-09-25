"""Публичная витрина health микросервисов (anonymous route, не команда)."""

from typing import Annotated

from fastapi import APIRouter, Query

from apps.frontend.di import Di
from apps.frontend.models import ServiceStatus
from apps.frontend.services.service_health import collect_services_status
from core.pagination import OffsetPage

router = APIRouter(prefix="/api/services", tags=["services"])


@router.get("/status", response_model=OffsetPage[ServiceStatus])
async def get_services_status(
    di: Di,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[ServiceStatus]:
    return await collect_services_status(di.service_client, limit=limit, offset=offset)
