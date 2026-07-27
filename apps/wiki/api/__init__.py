"""API роутеры сервиса wiki."""

from fastapi import APIRouter

from apps.wiki.api.access import router as access_router
from apps.wiki.api.backlinks import router as backlinks_router
from apps.wiki.api.comments import router as comments_router
from apps.wiki.api.namespaces import router as namespaces_router
from apps.wiki.api.pages import router as pages_router
from apps.wiki.api.public import router as public_router
from apps.wiki.api.revisions import router as revisions_router
from apps.wiki.api.search import router as search_router


def get_api_router() -> APIRouter:
    router = APIRouter()
    # Публичные маршруты идут первыми: их префикс не пересекается с /pages,
    # но порядок фиксирует намерение — анонимный доступ не должен зависеть
    # от появления новых защищённых путей.
    router.include_router(public_router)
    router.include_router(namespaces_router)
    router.include_router(pages_router)
    router.include_router(access_router)
    router.include_router(revisions_router)
    router.include_router(comments_router)
    router.include_router(search_router)
    router.include_router(backlinks_router)
    return router


__all__ = ["get_api_router"]
