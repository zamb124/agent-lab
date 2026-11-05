"""API роутеры сервиса geo."""

from fastapi import APIRouter

from apps.geo.api.geo import router as geo_router
from apps.geo.api.tiles import router as tiles_router


def get_api_router() -> APIRouter:
    router = APIRouter()
    router.include_router(geo_router)
    router.include_router(tiles_router)
    return router


__all__ = ["get_api_router"]
