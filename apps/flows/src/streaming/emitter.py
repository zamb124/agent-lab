"""
Emitter - публикация A2A событий в Redis Pub/Sub.
"""

import json
from typing import Any, Dict, Optional

from core.clients import RedisClient
from core.logging import get_logger
from core.state import ExecutionState
from .base import BaseEmitter

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
    
    def __init__(self, redis_client: RedisClient, state: ExecutionState):
        """
        Args:
            redis_client: Redis клиент для pub/sub
            state: ExecutionState с task_id, context_id
        """
        super().__init__(state)
        self.redis = redis_client

    async def _publish(self, event: Any) -> None:
        """
        Публикует событие в Redis с автоматическим добавлением trace контекста.
        
        Args:
            event: A2A событие
        """
        event_dict = event.model_dump() if hasattr(event, "model_dump") else event
        
        if self._span_context:
            if "metadata" not in event_dict:
                event_dict["metadata"] = {}
            event_dict["metadata"]["trace_id"] = self._span_context.get("trace_id")
            event_dict["metadata"]["span_id"] = self._span_context.get("span_id")
        
        channel = f"stream:{self.state.task_id}"
        event_kind = event_dict.get("kind", "unknown")
        logger.debug(f"[Emitter] Publishing {event_kind} to {channel}")
        await self.redis.publish(
            channel,
            json.dumps(event_dict, default=str, ensure_ascii=False),
        )
        logger.debug(f"[Emitter] Published {event_kind} to {channel}")

    async def emit_ui_event(
        self,
        event_type: str,
        payload: Dict[str, Any],
        *,
        event_id: Optional[str] = None,
        version: str = "1.0.0",
        timestamp: str,
        source: str = "assistant",
        correlation_id: Optional[str] = None,
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
