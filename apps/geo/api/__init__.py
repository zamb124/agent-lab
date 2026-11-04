"""API роутеры сервиса geo."""

from fastapi import APIRouter

from apps.geo.api.geo import router as geo_router


def get_api_router() -> APIRouter:
    router = APIRouter()
    router.include_router(geo_router)
    return router


__all__ = ["get_api_router"]
