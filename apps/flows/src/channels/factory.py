"""ChannelFactory — создание каналов по имени."""

from __future__ import annotations

import importlib
from collections.abc import Mapping
from typing import TYPE_CHECKING, Protocol, TypeVar, cast

from apps.flows.src.container_contracts import FlowRuntimeContainer

if TYPE_CHECKING:
    from apps.flows.src.channels.a2a import A2AChannel

ChannelT = TypeVar("ChannelT", bound="ChannelClass")


class ChannelClass(Protocol):
    name: str

    def __call__(
        self,
        flow_id: str,
        context: object | None = None,
        *,
        container: FlowRuntimeContainer,
    ) -> A2AChannel: ...

_CHANNEL_REGISTRY: dict[str, str] = {
    "a2a": "apps.flows.src.channels.a2a:A2AChannel",
    "telegram": "apps.flows.src.channels.trigger_telegram_channel:TelegramInboundChannel",
    "websocket": "apps.flows.src.channels.websocket:WebSocketChannel",
}


def _load_channel_class(path: str) -> ChannelClass:
    module_path, class_name = path.split(":", 1)
    module = importlib.import_module(module_path)
    module_attrs = cast(Mapping[str, object], vars(module))
    cls = module_attrs.get(class_name)
    if cls is None:
        raise ValueError(f"Channel class not found: {path}")
    return cast(ChannelClass, cls)


def register_channel(channel_class: type[ChannelT]) -> type[ChannelT]:
    """Декоратор для регистрации канала."""
    _CHANNEL_REGISTRY[channel_class.name] = (
        f"{channel_class.__module__}:{channel_class.__qualname__}"
    )
    return channel_class


def get_channel(
    name: str,
    flow_id: str,
    context: object | None = None,
    *,
    container: FlowRuntimeContainer,
) -> A2AChannel:
    """
    Получить канал по имени.

    Аргументы:
        name: Имя канала ("a2a", "telegram", "whatsapp")
        flow_id: ID агента для канала
        context: Context с данными пользователя (опционально)

    Возвращает:
        Экземпляр канала

    Исключения:
        ValueError: Если канал не зарегистрирован
    """
    if name not in _CHANNEL_REGISTRY:
        raise ValueError(f"Unknown channel: {name}. Available: {list(_CHANNEL_REGISTRY.keys())}")

    channel_class = _load_channel_class(_CHANNEL_REGISTRY[name])
    return channel_class(flow_id, context=context, container=container)
