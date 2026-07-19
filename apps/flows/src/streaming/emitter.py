"""
Emitter - публикация A2A событий в Redis Pub/Sub.
"""

import json
from datetime import datetime, timezone
from typing import override

from a2a.types import StreamResponse, TaskStatusUpdateEvent
from google.protobuf.json_format import MessageToDict

from apps.flows.src.observability.flow_timing import maybe_record_flow_first_content_chunk
from core.a2a import struct_from_mapping
from core.clients.redis_client import RedisClient
from core.logging import get_logger
from core.state import ExecutionState
from core.types import JsonObject, require_json_object

from .base import BaseEmitter, StreamEvent

logger = get_logger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Emitter(BaseEmitter):
    """
    Публикация событий в Redis Pub/Sub.

    Все события автоматически получают:
    - task_id
    - context_id
    - trace_id (из OpenTelemetry контекста)
    - span_id (из OpenTelemetry контекста)

    Примеры:
        >>> emitter = Emitter(redis, state)
        >>> await emitter.emit_text("Привет")
        >>> await emitter.emit_complete("Готово")
    """

    redis: RedisClient
    _first_content_chunk_recorded: bool

    def __init__(self, redis_client: RedisClient, state: ExecutionState):
        """
        Аргументы:
            redis_client: Redis клиент для pub/sub
            state: ExecutionState с task_id, context_id
        """
        super().__init__(state)
        self.redis = redis_client
        self._first_content_chunk_recorded = False

    @override
    async def emit_text(
        self,
        text: str,
        append: bool = True,
        last_chunk: bool = False,
        *,
        artifact_name: str = "response",
    ) -> None:
        if (
            artifact_name == "response"
            and text != ""
            and not self._first_content_chunk_recorded
        ):
            self._first_content_chunk_recorded = True
            flow_id = self.state.session_flow_id
            await maybe_record_flow_first_content_chunk(
                self.redis,
                task_id=self.state.task_id,
                flow_id=flow_id,
                text=text,
            )
        await super().emit_text(
            text,
            append=append,
            last_chunk=last_chunk,
            artifact_name=artifact_name,
        )

    @override
    async def _publish(self, event: StreamEvent) -> None:
        """
        Публикует событие в Redis как A2A 1.0 StreamResponse (MessageToDict).

        Аргументы:
            event: A2A событие
        """
        if self._span_context:
            meta: JsonObject = {
                "trace_id": self._span_context.get("trace_id"),
                "span_id": self._span_context.get("span_id"),
            }
            if event.HasField("metadata"):
                existing = require_json_object(
                    MessageToDict(event.metadata),
                    "StreamEvent.metadata",
                )
                meta = {**existing, **meta}
            event.metadata.CopyFrom(struct_from_mapping(meta))

        if isinstance(event, TaskStatusUpdateEvent):
            stream = StreamResponse(status_update=event)
            event_kind = "statusUpdate"
        else:
            stream = StreamResponse(artifact_update=event)
            event_kind = "artifactUpdate"

        event_dict = MessageToDict(stream)
        channel = f"stream:{self.state.task_id}"
        logger.debug(f"[Emitter] Publishing {event_kind} to {channel}")
        _ = await self.redis.publish(
            channel,
            json.dumps(event_dict, ensure_ascii=False),
        )
        logger.debug(f"[Emitter] Published {event_kind} to {channel}")

    async def emit_handoff_initiated(
        self,
        target_flow_id: str,
        target_flow_name: str,
        handoff_reason: str | None,
        depth: int,
        child_session_id: str,
        trace_id: str | None = None,
    ) -> None:
        """Публикует ui_event platform.handoff_initiated для UI."""
        payload: JsonObject = {
            "target_flow_id": target_flow_id,
            "target_flow_name": target_flow_name,
            "handoff_reason": handoff_reason or "",
            "depth": depth,
            "child_session_id": child_session_id,
        }
        if trace_id is not None:
            payload["trace_id"] = trace_id
        await self.emit_ui_event(
            event_type="platform.handoff_initiated",
            payload=payload,
            timestamp=_utc_now_iso(),
        )

    async def emit_handback_completed(
        self,
        response: str,
        handoff_depth: int,
        child_flow_id: str,
        child_flow_name: str,
        parent_flow_name: str,
        trace_id: str | None = None,
    ) -> None:
        """Публикует ui_event platform.handback_completed для UI."""
        payload: JsonObject = {
            "response": response,
            "handoff_depth": handoff_depth,
            "child_flow_id": child_flow_id,
            "child_flow_name": child_flow_name,
            "parent_flow_name": parent_flow_name,
        }
        if trace_id is not None:
            payload["trace_id"] = trace_id
        await self.emit_ui_event(
            event_type="platform.handback_completed",
            payload=payload,
            timestamp=_utc_now_iso(),
        )

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


__all__ = ["Emitter"]
