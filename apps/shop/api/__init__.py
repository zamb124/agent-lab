"""API роутеры сервиса shop."""

from fastapi import APIRouter

from apps.shop.api.demos import router as demos_router
from apps.shop.api.internal import router as internal_router
from apps.shop.api.public import router as public_router
from apps.shop.api.shops import router as shops_router


def get_api_router() -> APIRouter:
    router = APIRouter()
    # Публичные маршруты идут первыми: анонимная витрина и агрегатор
    # не должны зависеть от появления новых защищённых путей.
    router.include_router(public_router)
    router.include_router(internal_router)
    router.include_router(demos_router)
    router.include_router(shops_router)
    return router


__all__ = ["get_api_router"]
