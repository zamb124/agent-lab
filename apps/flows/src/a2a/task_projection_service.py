"""Atomic A2A projection-before-publication application service."""

from __future__ import annotations

import json
from typing import final
from uuid import uuid4

from a2a.types import (
    TaskArtifactUpdateEvent,
    TaskStatusUpdateEvent,
)

from apps.flows.src.models.a2a_projection import A2ATaskEvent, A2ATaskProjection
from core.a2a import mapping_from_struct, stream_response_from_event, struct_from_mapping
from core.a2a.codec import stream_response_to_json_dict
from core.clients.redis_client import RedisClient
from core.logging import get_logger
from core.types import JsonObject, require_json_object

logger = get_logger(__name__)

StreamEvent = TaskArtifactUpdateEvent | TaskStatusUpdateEvent


def _event_identity(event: StreamEvent) -> str:
    metadata = mapping_from_struct(event.metadata) if event.HasField("metadata") else {}
    existing = metadata.get("platformEventId")
    if existing is not None:
        if not isinstance(existing, str) or existing.strip() == "":
            raise ValueError("A2A event metadata.platformEventId must be a non-empty string")
        return existing
    identity = str(uuid4())
    metadata["platformEventId"] = identity
    event.metadata.CopyFrom(struct_from_mapping(metadata))
    return identity


@final
class A2ATaskProjectionService:
    """Commits exact events before exposing them through the ephemeral live tail."""

    def __init__(
        self,
        *,
        redis_client: RedisClient,
    ) -> None:
        self._redis: RedisClient = redis_client

    @property
    def redis_client(self) -> RedisClient:
        return self._redis

    async def publish(self, *, company_id: str, event: StreamEvent) -> StreamEvent:
        """Persist/enrich one event, publish exact stored bytes, acknowledge delivery."""
        identity = _event_identity(event)
        appended = await A2ATaskProjection.append_event(
            company_id=company_id,
            event=event,
            event_identity=identity,
        )
        await self._publish_stored(appended.event)
        await A2ATaskEvent.mark_published_by_event_identity(
            company_id=company_id,
            task_id=appended.event.task_id,
            event_identity=identity,
        )
        return appended.event

    async def recover_unpublished(self, *, limit: int = 100) -> int:
        """Republish committed outbox rows after a Redis/process failure."""
        pending = await A2ATaskEvent.pending_events_by_created_at(limit=limit)
        for item in pending:
            await self._publish_stored(item.event)
            await A2ATaskEvent.mark_published_by_event_identity(
                company_id=item.company_id,
                task_id=item.task_id,
                event_identity=item.event_identity,
            )
        return len(pending)

    async def _publish_stored(self, event: StreamEvent) -> None:
        stream = stream_response_from_event(event)
        event_dict = stream_response_to_json_dict(stream)
        channel = f"stream:{event.task_id}"
        event_kind = (
            "artifactUpdate"
            if isinstance(event, TaskArtifactUpdateEvent)
            else "statusUpdate"
        )
        logger.debug(
            "a2a.stream.publish",
            event_kind=event_kind,
            task_id=event.task_id,
            channel=channel,
        )
        payload: JsonObject = require_json_object(event_dict, "A2A StreamResponse")
        _ = await self._redis.publish(
            channel,
            json.dumps(payload, ensure_ascii=False),
        )


__all__ = ["A2ATaskProjectionService"]
