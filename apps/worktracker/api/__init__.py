"""API роутеры сервиса worktracker."""

from fastapi import APIRouter

from apps.worktracker.api.boards import router as boards_router
from apps.worktracker.api.work_items import router as work_items_router
from apps.worktracker.api.work_queues import router as work_queues_router


def get_api_router() -> APIRouter:
    router = APIRouter()
    router.include_router(work_items_router)
    router.include_router(work_queues_router)
    router.include_router(boards_router)
    return router
