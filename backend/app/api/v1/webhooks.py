"""
Простые webhook эндпоинты для внешних интеграций.
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Dict, Any

router = APIRouter()


class WebhookPayload(BaseModel):
    """Базовая модель для webhook данных"""

    platform: str  # telegram, slack, etc.
    data: Dict[str, Any]


@router.post("/webhook/{platform}")
async def handle_webhook(platform: str, payload: WebhookPayload):
    """
    Универсальный webhook для всех платформ.
    Пока просто логируем, потом добавим обработку.
    """
    # TODO: Добавить обработку webhook'ов
    return {
        "status": "received",
        "platform": platform,
        "message": "Webhook received successfully",
    }


@router.get("/webhook/test")
async def test_webhook():
    """Тестовый эндпоинт для проверки API"""
    return {"message": "Webhook API working"}
