"""
Channels - каналы коммуникации и отправки сообщений.

Содержит:
1. BaseChannel - базовый класс каналов коммуникации (A2A, WebSocket, Telegram)
2. BaseChannelHandler - базовый класс для отправки сообщений в каналы
3. Конкретные реализации: TelegramChannelHandler, WebhookChannelHandler, EmailChannelHandler, SmsChannelHandler
4. ChannelRegistry - реестр handlers для отправки

Используется:
- ChannelNode (нода графа)
- TriggerExecutor (output_actions)
- A2A API, WebSocket API
"""

# Существующие классы каналов коммуникации
from .base import BaseChannel, BaseChannelHandler, PermissionDenied
from .email import EmailChannelHandler
from .registry import ChannelRegistry, create_default_channel_registry
from .sms import SmsChannelHandler
from .telegram import TelegramChannelHandler
from .webhook import WebhookChannelHandler

__all__ = [
    # Каналы коммуникации
    "BaseChannel",
    "PermissionDenied",
    # Handlers для отправки
    "BaseChannelHandler",
    "ChannelRegistry",
    "TelegramChannelHandler",
    "WebhookChannelHandler",
    "EmailChannelHandler",
    "SmsChannelHandler",
    "create_default_channel_registry",
]
