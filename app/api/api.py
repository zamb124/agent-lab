"""
Главный API роутер - объединяет все суброутеры API
"""

from fastapi import APIRouter

# Импорт роутера v1
from app.api.v1_router import router as v1_router

# Импорт других роутеров
from app.api.amocrm import router as amocrm_router
from app.api.v1.auth import router as auth_router
from app.api.v1.history import router as history_router
from app.api.v1.profiling import router as profiling_router
from app.frontend.api.mcp import router as mcp_router

# Создание главного API роутера
router = APIRouter(tags=["api"])

# Включение суброутеров
router.include_router(v1_router, prefix="/api/v1")
router.include_router(history_router, tags=["История и аналитика"])
router.include_router(profiling_router, tags=["profiling"], include_in_schema=False)
router.include_router(mcp_router, tags=["MCP"], include_in_schema=False)
router.include_router(auth_router, prefix="/auth", tags=["auth"], include_in_schema=False)
router.include_router(amocrm_router, prefix="/api/amocrm", tags=["amocrm"], include_in_schema=False)
