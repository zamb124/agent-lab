"""
Модуль для стриминга событий.

Иерархия классов:
- BaseEmitter -> Emitter (Redis), InMemoryEmitter
- BaseSubscriber -> EventSubscriber (Redis), InMemorySubscriber
"""

from .base import BaseEmitter, BaseSubscriber, StreamEvent
from .emitter import Emitter, RedisEmitter
from .memory import InMemoryEmitter, InMemorySubscriber
from .subscriber import EventSubscriber, RedisSubscriber, parse_event, is_final_event

__all__ = [
    "BaseEmitter",
    "BaseSubscriber",
    "StreamEvent",
    "Emitter",
    "RedisEmitter",
    "InMemoryEmitter",
    "InMemorySubscriber",
    "EventSubscriber",
    "RedisSubscriber",
    "parse_event",
    "is_final_event",
]
