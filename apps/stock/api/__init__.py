"""API роутеры сервиса stock."""

from fastapi import APIRouter

from apps.stock.api.catalog import router as catalog_router
from apps.stock.api.internal import router as internal_router
from apps.stock.api.transfers import router as transfers_router


def get_api_router() -> APIRouter:
    router = APIRouter()
    router.include_router(catalog_router)
    router.include_router(transfers_router)
    router.include_router(internal_router)
    return router
