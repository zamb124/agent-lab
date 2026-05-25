"""
Emitter - публикация A2A событий в Redis Pub/Sub.
"""

import json
from typing import override

from core.clients.redis_client import RedisClient
from core.logging import get_logger
from core.state import ExecutionState
from core.types import JsonObject, parse_json_object, require_json_object

from .base import BaseEmitter, StreamEvent

logger = get_logger(__name__)


class Emitter(BaseEmitter):
    """
    Публикация событий в Redis Pub/Sub.

    Все события автоматически получают:
    - task_id
    - context_id
    - trace_id (из OpenTelemetry контекста)
    - span_id (из OpenTelemetry контекста)

    Examples:
        >>> emitter = Emitter(redis, state)
        >>> await emitter.emit_text("Hello")
        >>> await emitter.emit_complete("Done")
    """

    redis: RedisClient

    def __init__(self, redis_client: RedisClient, state: ExecutionState):
        """
        Args:
            redis_client: Redis клиент для pub/sub
            state: ExecutionState с task_id, context_id
        """
        super().__init__(state)
        self.redis = redis_client

    @override
    async def _publish(self, event: StreamEvent) -> None:
        """
        Публикует событие в Redis с автоматическим добавлением trace контекста.

        Args:
            event: A2A событие
        """
        event_dict = parse_json_object(event.model_dump_json(), "StreamEvent")

        if self._span_context:
            metadata = event_dict.get("metadata")
            if metadata is None:
                metadata_obj: JsonObject = {}
            else:
                metadata_obj = require_json_object(metadata, "StreamEvent.metadata")
            metadata_obj["trace_id"] = self._span_context.get("trace_id")
            metadata_obj["span_id"] = self._span_context.get("span_id")
            event_dict["metadata"] = metadata_obj

        channel = f"stream:{self.state.task_id}"
        raw_event_kind = event_dict.get("kind")
        event_kind = raw_event_kind if isinstance(raw_event_kind, str) else "unknown"
        logger.debug(f"[Emitter] Publishing {event_kind} to {channel}")
        _ = await self.redis.publish(
            channel,
            json.dumps(event_dict, ensure_ascii=False),
        )
        logger.debug(f"[Emitter] Published {event_kind} to {channel}")

    @override
    async def emit_ui_event(
        self,
        event_type: str,
        payload: JsonObject,
        *,
        event_id: str | None = None,
        version: str = "1.0.0",
        timestamp: str,
        source: str = "assistant",
        correlation_id: str | None = None,
    ) -> None:
        await super().emit_ui_event(
            event_type=event_type,
            payload=payload,
            event_id=event_id,
            version=version,
            timestamp=timestamp,
            source=source,
            correlation_id=correlation_id,
        )


# Алиас для обратной совместимости
RedisEmitter = Emitter


__all__ = ["Emitter", "RedisEmitter"]
