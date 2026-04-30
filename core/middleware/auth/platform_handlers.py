"""
Обработчики для платформ (Telegram, WhatsApp).
"""

import json

from core.logging import get_logger
from typing import Optional, Tuple
from fastapi import Request, HTTPException

from core.models.identity_models import User, Company, UserStatus, AuthProvider

logger = get_logger(__name__)
class PlatformHandler:
    """Базовый обработчик платформы"""
    
    def __init__(self, container):
        self.container = container
    
    async def extract_company_from_webhook_path(self, path: str, platform: str) -> Company:
        """Извлекает компанию из пути webhook"""
        prefix = f"/flows/api/v1/webhook/{platform}/"
        if not path.startswith(prefix):
            raise HTTPException(status_code=400, detail=f"Invalid webhook path: {path}")
        
        flow_key = path[len(prefix):]
        parts = flow_key.split(":")
        
        if len(parts) < 4 or parts[0] != "company" or parts[2] != "flow":
            raise HTTPException(status_code=400, detail=f"Invalid flow key format: {flow_key}")
        
        company_id = parts[1]
        company = await self.container.company_repository.get(company_id)
        
        if not company:
            raise HTTPException(status_code=404, detail=f"Company {company_id} not found")
        
        return company

class TelegramHandler(PlatformHandler):
    """Обработчик Telegram webhook"""
    
    async def create_user_from_request(self, request: Request, company: Company) -> Tuple[User, dict]:
        """Создает пользователя из Telegram webhook данных"""
        body = await request.body()
        data = json.loads(body)
        
        tg_user = data.get("message", {}).get("from", {})
        telegram_user_id = str(tg_user.get("id", "unknown"))
        username = tg_user.get("username", "")
        first_name = tg_user.get("first_name", "")
        last_name = tg_user.get("last_name", "")
        
        full_name = f"{first_name} {last_name}".strip() or username or f"User_{telegram_user_id}"
        
        user = User(
            user_id=f"telegram_{telegram_user_id}",
            provider=AuthProvider.YANDEX,
            provider_user_id=telegram_user_id,
            email="",
            name=full_name,
            status=UserStatus.ACTIVE,
            groups=["user"],
            companies={company.company_id: ["user"]},
            active_company_id=company.company_id,
        )
        
        metadata = {
            "telegram_user_id": telegram_user_id,
            "username": username,
            "first_name": first_name,
            "last_name": last_name,
        }
        
        return user, metadata

class WhatsAppHandler(PlatformHandler):
    """Обработчик WhatsApp webhook"""
    
    async def create_user_from_request(self, request: Request, company: Company) -> Tuple[User, dict]:
        """Создает пользователя из WhatsApp webhook данных"""
        body = await request.body()
        data = json.loads(body)
        
        entry = data.get("entry", [{}])[0]
        changes = entry.get("changes", [{}])
        value = changes[0].get("value", {}) if changes else {}
        
        messages = value.get("messages", [])
        contacts = value.get("contacts", [])
        
        phone_number = "unknown"
        if messages:
            phone_number = messages[0].get("from", "unknown")
        
        profile_name = "User"
        if contacts:
            profile_name = contacts[0].get("profile", {}).get("name", "User")
        
        user = User(
            user_id=f"whatsapp_{phone_number}",
            provider=AuthProvider.YANDEX,
            provider_user_id=phone_number,
            email="",
            name=profile_name,
            status=UserStatus.ACTIVE,
            groups=["user"],
            companies={company.company_id: ["user"]},
            active_company_id=company.company_id,
        )
        
        metadata = {
            "whatsapp_phone": phone_number,
            "profile_name": profile_name,
        }
        
        return user, metadata

def get_platform_handler(platform: str, container) -> Optional[PlatformHandler]:
    """Возвращает обработчик для платформы"""
    handlers = {
        "telegram": TelegramHandler,
        "whatsapp": WhatsAppHandler,
    }
    handler_class = handlers.get(platform)
    if handler_class:
        return handler_class(container)
    return None

