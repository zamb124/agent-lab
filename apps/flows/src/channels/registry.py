"""
ChannelRegistry - реестр channel handlers.

Регистрирует handlers для каждого типа канала.
"""

from __future__ import annotations

from apps.flows.src.models.enums import ChannelType
from core.logging import get_logger
from core.mail.service import MailService

from .base import BaseChannelHandler
from .email import EmailChannelHandler
from .sms import SmsChannelHandler
from .telegram import TelegramChannelHandler
from .webhook import WebhookChannelHandler

logger = get_logger(__name__)


class ChannelRegistry:
    """
    Реестр channel handlers.

    При startup регистрируются все доступные каналы:
    - ChannelType.TELEGRAM → TelegramChannelHandler
    - ChannelType.WEBHOOK → WebhookChannelHandler
    - ChannelType.EMAIL → EmailChannelHandler (требует mail_service)
    - ChannelType.SMS → SmsChannelHandler
    """

    def __init__(self) -> None:
        self._handlers: dict[ChannelType, type[BaseChannelHandler]] = {}
        self._instances: dict[ChannelType, BaseChannelHandler] = {}

    def register(
        self,
        channel_type: ChannelType,
        handler_class: type[BaseChannelHandler],
    ) -> None:
        """
        Регистрирует handler для канала.

        Аргументы:
            channel_type: Тип канала
            handler_class: Класс handler'а
        """
        self._handlers[channel_type] = handler_class
        logger.debug("flows.channel.registered", channel_type=channel_type.value)

    def get(
        self,
        channel_type: ChannelType | str,
        *,
        mail_service: MailService | None = None,
    ) -> BaseChannelHandler:
        """
        Возвращает handler для канала.

        Аргументы:
            channel_type: Тип канала (enum или строка, например \"telegram\")
            mail_service: обязателен для ChannelType.EMAIL

        Возвращает:
            Экземпляр handler'а (singleton per channel type, кроме email — per mail_service)

        Исключения:
            ValueError: Если канал не зарегистрирован или нет mail_service для email
        """
        if not isinstance(channel_type, ChannelType):
            channel_type = ChannelType(channel_type)

        if channel_type is ChannelType.EMAIL:
            if mail_service is None:
                raise ValueError("Email channel requires mail_service")
            return EmailChannelHandler(mail_service)

        if channel_type in self._instances:
            return self._instances[channel_type]

        handler_class = self._handlers.get(channel_type)

        if handler_class is None:
            available = [ct.value for ct in self._handlers.keys()]
            raise ValueError(
                f"Unknown channel type: {channel_type.value}. Available: {', '.join(available)}"
            )

        instance = handler_class()
        self._instances[channel_type] = instance
        return instance

    def has(self, channel_type: ChannelType | str) -> bool:
        """Проверяет зарегистрирован ли канал."""
        if not isinstance(channel_type, ChannelType):
            channel_type = ChannelType(channel_type)
        return channel_type in self._handlers

    def list_channels(self) -> list[str]:
        """Возвращает список зарегистрированных каналов."""
        return [ct.value for ct in self._handlers.keys()]

    def __len__(self) -> int:
        return len(self._handlers)


def create_default_channel_registry() -> ChannelRegistry:
    """
    Создает ChannelRegistry с зарегистрированными handlers.

    Вызывается при startup приложения.
    """
    registry = ChannelRegistry()

    registry.register(ChannelType.TELEGRAM, TelegramChannelHandler)
    registry.register(ChannelType.WEBHOOK, WebhookChannelHandler)
    registry.register(ChannelType.EMAIL, EmailChannelHandler)
    registry.register(ChannelType.SMS, SmsChannelHandler)

    logger.info("flows.channel.registry_created", count=len(registry))

    return registry


__all__ = ["ChannelRegistry", "create_default_channel_registry"]
