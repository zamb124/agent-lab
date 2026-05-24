"""
ChannelRegistry - реестр channel handlers.

Регистрирует handlers для каждого типа канала.
"""


from apps.flows.src.models.enums import ChannelType
from core.logging import get_logger

from .base import BaseChannelHandler
from .telegram import TelegramChannelHandler
from .webhook import WebhookChannelHandler

logger = get_logger(__name__)


class ChannelRegistry:
    """
    Реестр channel handlers.

    При startup регистрируются все доступные каналы:
    - ChannelType.TELEGRAM → TelegramChannelHandler
    - ChannelType.WEBHOOK → WebhookChannelHandler
    - и т.д.
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

        Args:
            channel_type: Тип канала
            handler_class: Класс handler'а
        """
        self._handlers[channel_type] = handler_class
        logger.debug(f"Channel handler registered: {channel_type.value}")

    def get(self, channel_type: ChannelType | str) -> BaseChannelHandler:
        """
        Возвращает handler для канала.

        Args:
            channel_type: Тип канала (enum или строка, например \"telegram\")

        Returns:
            Экземпляр handler'а (singleton per channel type)

        Raises:
            ValueError: Если канал не зарегистрирован
        """
        if not isinstance(channel_type, ChannelType):
            channel_type = ChannelType(channel_type)

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

    logger.info(f"Channel registry created with {len(registry)} handlers")

    return registry


__all__ = ["ChannelRegistry", "create_default_channel_registry"]
