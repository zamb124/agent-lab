"""
Debug API для тестов.

Используется для диагностики работы сервиса в тестах.
"""

from fastapi import APIRouter

from core.config import get_settings
from apps.frontend.container import get_frontend_container

router = APIRouter(prefix="/debug", tags=["debug"])


@router.get("/check-user/{user_id}")
async def check_user(user_id: str):
    """
    Проверяет существование пользователя в БД.
    Используется для диагностики в E2E тестах.
    """
    container = get_frontend_container()
    settings = get_settings()
    
    try:
        user = await container.user_repository.get(user_id)
        shared_db_url = settings.database.shared_url
        return {
            "exists": user is not None,
            "user_id": user_id,
            "user_name": user.name if user else None,
            "shared_db_url": shared_db_url[:50] + "..." if shared_db_url else None
        }
    except Exception as e:
        return {
            "exists": False,
            "user_id": user_id,
            "error": str(e)
        }


@router.get("/health")
async def debug_health():
    """Debug health check"""
    return {"status": "ok", "service": "frontend"}

