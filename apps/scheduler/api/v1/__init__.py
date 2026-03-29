"""API v1 роутеры scheduler."""

from fastapi import APIRouter

from apps.scheduler.api.v1.schedules import router as schedules_router

api_v1_router = APIRouter()
api_v1_router.include_router(schedules_router)
