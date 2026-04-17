"""
TelegramChannelHandler - отправка сообщений через Telegram Bot API.
"""

import os
from typing import Any, Dict, Optional, Union

from apps.flows.src.models.enums import ChannelType
from core.http import get_httpx_client
from core.logging import get_logger

from .base import BaseChannelHandler

logger = get_logger(__name__)


def get_telegram_api_base(config: Dict[str, Any] = None) -> str:
    """
    Возвращает базовый URL для Telegram API.
    
    Приоритет:
    1. config["api_base"] - для тестов
    2. TELEGRAM_API_BASE env - для тестов
    3. https://api.telegram.org - production
    """
    if config and config.get("api_base"):
        return config["api_base"]
    from core.config import get_settings
    return get_settings().telegram.api_base


class TelegramChannelHandler(BaseChannelHandler):
    """
    Handler для отправки сообщений через Telegram Bot API.
    
    Поддерживаемые действия:
    - send_message: текстовое сообщение
    - send_photo: фото с опциональной подписью
    - send_document: документ/файл
    - reply: ответ на сообщение
    
    Конфигурация:
    {
        "bot_token": "@var:my_bot_token" или прямое значение,
        "parse_mode": "HTML" | "Markdown" | "MarkdownV2",
        "disable_notification": false,
        "protect_content": false
    }
    """
    
    channel_type = ChannelType.TELEGRAM
    
    async def send_message(
        self,
        recipient: str,
        text: str,
        config: Dict[str, Any],
        variables: Dict[str, Any],
        reply_to_message_id: Optional[int] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Отправляет текстовое сообщение в Telegram."""
        bot_token = self._get_bot_token(config, variables)
        url = f"{get_telegram_api_base(config)}/bot{bot_token}/sendMessage"
        
        payload = {
            "chat_id": recipient,
            "text": text,
            "parse_mode": config.get("parse_mode", "HTML"),
        }
        
        if reply_to_message_id:
            payload["reply_to_message_id"] = reply_to_message_id
        
        if config.get("disable_notification"):
            payload["disable_notification"] = True
            
        if config.get("protect_content"):
            payload["protect_content"] = True
        
        async with get_httpx_client(timeout=30.0, proxy=True) as client:
            response = await client.post(url, json=payload)
            result = response.json()
            
            if not result.get("ok"):
                logger.error(
                    f"Telegram sendMessage failed: {result.get('description')}"
                )
                raise RuntimeError(
                    f"Telegram API error: {result.get('description', 'Unknown error')}"
                )
            
            logger.info(f"Telegram message sent to {recipient}")
            return result
    
    async def send_photo(
        self,
        recipient: str,
        photo: Union[str, bytes],
        config: Dict[str, Any],
        variables: Dict[str, Any],
        caption: Optional[str] = None,
        reply_to_message_id: Optional[int] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Отправляет фото в Telegram."""
        bot_token = self._get_bot_token(config, variables)
        url = f"{get_telegram_api_base(config)}/bot{bot_token}/sendPhoto"
        
        async with get_httpx_client(timeout=60.0, proxy=True) as client:
            if isinstance(photo, bytes):
                files = {"photo": ("photo.jpg", photo, "image/jpeg")}
                data = {"chat_id": recipient}
                
                if caption:
                    data["caption"] = caption
                    data["parse_mode"] = config.get("parse_mode", "HTML")
                    
                if reply_to_message_id:
                    data["reply_to_message_id"] = reply_to_message_id
                
                response = await client.post(url, data=data, files=files)
            else:
                payload = {
                    "chat_id": recipient,
                    "photo": photo,
                }
                
                if caption:
                    payload["caption"] = caption
                    payload["parse_mode"] = config.get("parse_mode", "HTML")
                    
                if reply_to_message_id:
                    payload["reply_to_message_id"] = reply_to_message_id
                
                response = await client.post(url, json=payload)
            
            result = response.json()
            
            if not result.get("ok"):
                logger.error(f"Telegram sendPhoto failed: {result.get('description')}")
                raise RuntimeError(
                    f"Telegram API error: {result.get('description', 'Unknown error')}"
                )
            
            logger.info(f"Telegram photo sent to {recipient}")
            return result
    
    async def send_document(
        self,
        recipient: str,
        document: Union[str, bytes],
        config: Dict[str, Any],
        variables: Dict[str, Any],
        caption: Optional[str] = None,
        filename: Optional[str] = None,
        reply_to_message_id: Optional[int] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Отправляет документ в Telegram."""
        bot_token = self._get_bot_token(config, variables)
        url = f"{get_telegram_api_base(config)}/bot{bot_token}/sendDocument"
        
        async with get_httpx_client(timeout=120.0, proxy=True) as client:
            if isinstance(document, bytes):
                fname = filename or "document"
                files = {"document": (fname, document, "application/octet-stream")}
                data = {"chat_id": recipient}
                
                if caption:
                    data["caption"] = caption
                    data["parse_mode"] = config.get("parse_mode", "HTML")
                    
                if reply_to_message_id:
                    data["reply_to_message_id"] = reply_to_message_id
                
                response = await client.post(url, data=data, files=files)
            else:
                payload = {
                    "chat_id": recipient,
                    "document": document,
                }
                
                if caption:
                    payload["caption"] = caption
                    payload["parse_mode"] = config.get("parse_mode", "HTML")
                    
                if reply_to_message_id:
                    payload["reply_to_message_id"] = reply_to_message_id
                
                response = await client.post(url, json=payload)
            
            result = response.json()
            
            if not result.get("ok"):
                logger.error(
                    f"Telegram sendDocument failed: {result.get('description')}"
                )
                raise RuntimeError(
                    f"Telegram API error: {result.get('description', 'Unknown error')}"
                )
            
            logger.info(f"Telegram document sent to {recipient}")
            return result
    
    async def reply(
        self,
        recipient: str,
        message_id: int,
        text: str,
        config: Dict[str, Any],
        variables: Dict[str, Any],
        **kwargs,
    ) -> Dict[str, Any]:
        """Отвечает на сообщение (reply)."""
        return await self.send_message(
            recipient=recipient,
            text=text,
            config=config,
            variables=variables,
            reply_to_message_id=message_id,
            **kwargs,
        )
    
    def _get_bot_token(
        self,
        config: Dict[str, Any],
        variables: Dict[str, Any],
    ) -> str:
        """Извлекает bot_token из конфига или variables."""
        bot_token = config.get("bot_token") or config.get("_bot_token_resolved")
        
        if not bot_token:
            raise ValueError("bot_token is required for Telegram channel")
        
        if bot_token.startswith("@var:"):
            var_key = bot_token[5:]
            resolved = variables.get(var_key)
            if not resolved:
                raise ValueError(f"Variable not found: {var_key}")
            return str(resolved)
        
        return bot_token


__all__ = ["TelegramChannelHandler"]
