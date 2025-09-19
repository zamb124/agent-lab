"""
API для работы с лидами
"""

import uuid
import httpx
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
import json

from app.core.storage import Storage
from app.core.config import settings

router = APIRouter()


class LeadRequest(BaseModel):
    message: str
    email: EmailStr
    phone: Optional[str] = None


class LeadResponse(BaseModel):
    id: str
    message: str
    status: str = "created"


@router.post("/lead", response_model=LeadResponse)
async def create_lead(lead: LeadRequest):
    """Создание нового лида"""
    
    try:
        # Генерируем ID для лида
        lead_id = str(uuid.uuid4())
        
        # Подготавливаем данные для сохранения
        lead_data = {
            "id": lead_id,
            "message": lead.message,
            "email": lead.email,
            "phone": lead.phone,
            "created_at": datetime.now().isoformat(),
            "status": "new"
        }
        
        # Сохраняем в базу данных
        storage = Storage()
        await storage.set(f"lead:{lead_id}", json.dumps(lead_data))
        
        # Отправляем уведомление в Telegram
        await send_telegram_notification(lead_data)
        
        return LeadResponse(
            id=lead_id,
            message="Лид успешно создан"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка создания лида: {str(e)}")


async def send_telegram_notification(lead_data: dict):
    """Отправка уведомления о новом лиде в Telegram"""
    
    try:
        # Получаем токен бота из конфигурации
        bot_token = settings.telegram.bots.get("agents_lab_info_bot")
        
        if not bot_token:
            print("❌ Токен бота agents_lab_info_bot не найден в конфигурации")
            return
            
        # Формируем сообщение
        message_parts = [
            "🆕 <b>Новый лид с сайта Agents Lab</b>",
            "",
            f"📧 <b>Email:</b> {lead_data['email']}",
        ]
        
        if lead_data.get('phone'):
            message_parts.append(f"📞 <b>Телефон:</b> {lead_data['phone']}")
            
        message_parts.extend([
            "",
            f"💬 <b>Сообщение:</b>",
            lead_data['message'],
            "",
            f"🆔 <b>ID лида:</b> {lead_data['id']}",
            f"⏰ <b>Время:</b> {lead_data['created_at']}"
        ])
        
        message_text = "\n".join(message_parts)
        
        # Отправляем напрямую через Telegram Bot API
        group_id = -4655393287
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        
        payload = {
            "chat_id": group_id,
            "text": message_text,
            "parse_mode": "HTML"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, timeout=10)
            
        if response.status_code == 200:
            print(f"✅ Уведомление о лиде {lead_data['id']} отправлено в Telegram")
        else:
            print(f"❌ Ошибка отправки в Telegram: {response.status_code} - {response.text}")
        
    except Exception as e:
        print(f"❌ Ошибка отправки в Telegram: {e}")
        # Не бросаем исключение, чтобы не нарушить основной процесс
