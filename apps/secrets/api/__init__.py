"""API роутеры сервиса secrets."""

from fastapi import APIRouter

from apps.secrets.api.variables import router as variables_router


def get_api_router() -> APIRouter:
    router = APIRouter()
    router.include_router(variables_router)
    return router
