"""API роутеры сервиса shop."""

from fastapi import APIRouter

from apps.shop.api.menu_imports import router as menu_imports_router
from apps.shop.api.public import router as public_router
from apps.shop.api.shops import router as shops_router


def get_api_router() -> APIRouter:
    router = APIRouter()
    # Публичные маршруты идут первыми: анонимная витрина и агрегатор
    # не должны зависеть от появления новых защищённых путей.
    router.include_router(public_router)
    # Раньше shops_router: ``/products/enrich`` не должен совпасть с ``/products/{product_id}``.
    router.include_router(menu_imports_router)
    router.include_router(shops_router)
    return router


__all__ = ["get_api_router"]
