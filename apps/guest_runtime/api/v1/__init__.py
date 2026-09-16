"""v1 API guest_runtime."""

from fastapi import APIRouter

from apps.guest_runtime.api.v1.farm import router as farm_router

router = APIRouter()
router.include_router(farm_router)
