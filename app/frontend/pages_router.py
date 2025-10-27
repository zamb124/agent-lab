"""
Frontend Pages роутер - объединяет все суброутеры frontend pages
"""

from fastapi import APIRouter

# Импорт всех frontend pages суброутеров
import app.frontend.pages.auth as auth_pages
import app.frontend.pages.dashboard as dashboard_pages
import app.frontend.pages.public as public_pages

# Создание главного frontend pages роутера
router = APIRouter(tags=["frontend-pages"])

# Включение суброутеров
router.include_router(public_pages.router, tags=["public-pages"], include_in_schema=False)
router.include_router(auth_pages.router, tags=["auth-pages"], include_in_schema=False)
router.include_router(dashboard_pages.router, tags=["dashboard-pages"], include_in_schema=False)
