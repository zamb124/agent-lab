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


from apps.agents.config import get_agents_settings
settings = get_agents_settings()

router = APIRouter(
    tags=["Лиды и заявки"],
    responses={
        400: {"description": "Неверные данные в заявке"},
        500: {"description": "Ошибка создания лида"}
    }
)


class LeadRequest(BaseModel):
    message: str
    email: EmailStr
    phone: Optional[str] = None


class LeadResponse(BaseModel):
    id: str
    message: str
    status: str = "created"


@router.post("/lead", response_model=LeadResponse, summary="Создать лид")
async def create_lead(lead: LeadRequest):
    """
    Создает лид (заявку) из формы обратной связи.
    
    Используется для сбора заявок с сайта, лендингов, форм обратной связи.
    
    **Что происходит:**
    1. Лид сохраняется в системе
    2. Опционально: отправляется в CRM (AmoCRM)
    3. Опционально: уведомление менеджерам
    
    **Обязательные поля:**
    - message - текст заявки/вопроса
    - email - контактный email
    
    **Опциональные:**
    - phone - телефон

    Args:
        lead: Данные заявки (сообщение, email, телефон)
        
    Returns:
        lead_id и статус создания
    """
    
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
            "💬 <b>Сообщение:</b>",
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
