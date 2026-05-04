"""
Модуль для стриминга событий.

Иерархия классов:
- BaseEmitter -> Emitter (Redis), InMemoryEmitter
- BaseSubscriber -> EventSubscriber (Redis), InMemorySubscriber
"""

from .base import BaseEmitter, BaseSubscriber, StreamEvent
from .emitter import Emitter, RedisEmitter
from .memory import InMemoryEmitter, InMemorySubscriber
from .speakable import (
    SPEAK_FLAG_KEY,
    SPEAKABLE_ARTIFACT_NAMES,
    extract_speakable_text,
    is_speakable_artifact,
    iter_speakable_text_parts,
)
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
    "SPEAKABLE_ARTIFACT_NAMES",
    "SPEAK_FLAG_KEY",
    "extract_speakable_text",
    "is_speakable_artifact",
    "iter_speakable_text_parts",
]
