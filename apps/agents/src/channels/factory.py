"""
ChannelFactory - создание каналов по имени.
"""

from typing import Dict, Type

from apps.agents.src.channels.a2a import A2AChannel
from apps.agents.src.channels.base import BaseChannel
from apps.agents.src.channels.websocket import WebSocketChannel


_CHANNEL_REGISTRY: Dict[str, Type[BaseChannel]] = {}


def register_channel(channel_class: Type[BaseChannel]) -> Type[BaseChannel]:
    """Декоратор для регистрации канала."""
    _CHANNEL_REGISTRY[channel_class.name] = channel_class
    return channel_class


def get_channel(name: str, agent_id: str, context=None) -> BaseChannel:
    """
    Получить канал по имени.
    
    Args:
        name: Имя канала ("a2a", "telegram", "whatsapp")
        agent_id: ID агента для канала
        context: Context с данными пользователя (опционально)
        
    Returns:
        Экземпляр канала
        
    Raises:
        ValueError: Если канал не зарегистрирован
    """
    if name not in _CHANNEL_REGISTRY:
        raise ValueError(f"Unknown channel: {name}. Available: {list(_CHANNEL_REGISTRY.keys())}")
    
    channel_class = _CHANNEL_REGISTRY[name]
    return channel_class(agent_id, context=context)


def _register_builtin_channels():
    """Регистрация встроенных каналов."""
    register_channel(A2AChannel)
    register_channel(WebSocketChannel)


_register_builtin_channels()

