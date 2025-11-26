"""
Инструменты для работы с Telegram каналами.
Позволяют публиковать посты в каналы через Telegram Bot API.
"""

import logging
import httpx
from typing import Optional

from apps.agents.services.tool_decorator import tool
from core.files.processors import get_default_file_processor
from core.context import get_context
from apps.agents.interfaces.telegram_interface import TelegramInterface

logger = logging.getLogger(__name__)


@tool(group="Социальные сети", cost=0.0, billing_name="telegram_publish_post")
async def publish_to_telegram_channel(
    channel_id: str,
    text: str,
    image_file_id: Optional[str] = None
) -> str:
    """
    Публикует пост в Telegram канал.
    Токен бота берется из platform config автоматически.
    
    Args:
        channel_id: ID канала (@channel_username или -100123456789)
        text: Текст поста (поддерживает HTML)
        image_file_id: ID файла изображения из системы (опционально)
        
    Returns:
        Сообщение о успешной публикации или ошибке
    """
    context = get_context()
    if not context or not context.flow_config:
        raise ValueError("Flow config недоступен в контексте")
    
    flow_config = context.flow_config
    telegram_config = flow_config.platforms.get("telegram")
    
    if not telegram_config:
        raise ValueError("Telegram не настроен для этого flow")
    
    # Получаем токен бота через TelegramInterface
    bot_token = await TelegramInterface.get_bot_token_for_flow(flow_config.flow_id, telegram_config)
    
    if not bot_token:
        raise ValueError("Не удалось получить токен бота")
    # Если есть изображение - публикуем с фото через sendPhoto
    if image_file_id:
        file_processor = await get_default_file_processor()
        file_record = await file_processor.get_file_record(image_file_id)
        
        if not file_record:
            raise ValueError(f"Файл {image_file_id} не найден в системе")
        
        s3_client = await file_processor._get_s3_client()
        image_data = await s3_client.download_bytes(file_record.s3_key)
        
        if not image_data:
            raise ValueError(f"Не удалось скачать изображение {image_file_id} из S3")
        
        url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
        
        files = {
            "photo": (file_record.original_name, image_data, file_record.content_type)
        }
        
        data = {
            "chat_id": channel_id,
            "caption": text,
            "parse_mode": "HTML"
        }
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, data=data, files=files)
    else:
        # Публикуем только текст через sendMessage
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        
        payload = {
            "chat_id": channel_id,
            "text": text,
            "parse_mode": "HTML"
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload)
    
    # Обрабатываем ответ
    if response.status_code != 200:
        error_text = response.text
        logger.error(f"❌ Ошибка Telegram API: {response.status_code} - {error_text}")
        raise httpx.HTTPStatusError(
            f"Telegram API ошибка: {response.status_code} - {error_text}",
            request=response.request,
            response=response
        )
    
    result = response.json()
    message_id = result.get("result", {}).get("message_id")
    post_type = "с изображением" if image_file_id else "текстовый"
    logger.info(f"✅ Пост {post_type} опубликован в канал {channel_id}, message_id={message_id}")
    return f"✅ Пост успешно опубликован в канал! (ID: {message_id})"


# Список инструментов для экспорта
TELEGRAM_CHANNEL_TOOLS = [
    publish_to_telegram_channel,
]

