"""API realtime bus."""

from fastapi import APIRouter

from apps.realtime.api.events import router as events_router
from apps.realtime.api.inbound import router as inbound_router
from apps.realtime.api.presence import router as presence_router


def get_api_router() -> APIRouter:
    router = APIRouter()
    router.include_router(inbound_router)
    router.include_router(presence_router)
    router.include_router(events_router)
    return router
