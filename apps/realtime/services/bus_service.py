"""Bus: persist PlatformEvent, XADD, Centrifugo publish, dispatch `_requested`."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from oxyde.exceptions import IntegrityError

from apps.realtime.db.models import PlatformEventLog
from core.clients.service_client import ServiceClient, ServiceClientError
from core.config import get_settings
from core.events.contract import (
    PLATFORM_EVENTS_STREAM,
    EventDelivery,
    PlatformEvent,
    PlatformEventMeta,
    assert_platform_event_type,
)
from core.events.redis_client import events_redis_client
from core.logging import get_logger
from core.push.delivery import deliver_offline_push
from core.realtime.centrifugo_client import centrifugo_presence_stats, centrifugo_publish
from core.realtime.channels import centrifugo_channels_for_delivery, user_channel
from core.realtime.command_owners import is_command_event_type, owner_service_for_event_type
from core.realtime.models import BusProcessingState
from core.types import JsonObject, require_json_object
from core.utils.time import utcnow

logger = get_logger(__name__)

_TERMINAL_FAILED_DETAIL = "deadline_exceeded"


class RealtimeBusService:
    async def ingest(self, event: PlatformEvent) -> PlatformEvent:
        _ = assert_platform_event_type(event.type)
        existing = await self._event(event.event_id)
        if existing is not None:
            return existing

        owner_service: str | None = None
        deadline_at: datetime | None = None
        processing_state = BusProcessingState.PUBLISHED
        if is_command_event_type(event.type):
            owner_service = owner_service_for_event_type(event.type)
            processing_state = BusProcessingState.RECEIVED
            deadline_at = datetime.now(timezone.utc) + timedelta(
                seconds=get_settings().realtime.command_deadline_seconds
            )

        inserted = await self.insert_if_absent(
            event,
            processing_state=processing_state,
            owner_service=owner_service,
            deadline_at=deadline_at,
        )
        if not inserted:
            stored = await self._event(event.event_id)
            if stored is None:
                raise RuntimeError(f"platform_event_log race: missing {event.event_id}")
            return stored

        await _xadd_platform_event(event)
        await self._publish_to_centrifugo(event)
        await self._maybe_offline_push(event)

        if is_command_event_type(event.type):
            await self._dispatch_command(event)
        return event

    async def get_event(self, event_id: str) -> PlatformEvent:
        stored = await self._event(event_id)
        if stored is None:
            raise KeyError(event_id)
        return stored

    async def get_terminal_for_causation(self, causation_id: str) -> PlatformEvent:
        stored = await self._terminal(causation_id)
        if stored is None:
            raise KeyError(causation_id)
        return stored

    async def sweep_expired_commands(self) -> int:
        now = datetime.now(timezone.utc)
        expired = await self._expired_commands(now=now, limit=100)
        swept = 0
        for command in expired:
            if await self._has_terminal(command.event_id):
                await self._set_processing_state(
                    command.event_id, BusProcessingState.PUBLISHED
                )
                continue
            failed = _deadline_failed_event(command)
            _ = await self.ingest(failed)
            await self._set_processing_state(
                command.event_id, BusProcessingState.DEADLINE_EXCEEDED
            )
            swept += 1
        return swept

    async def insert_if_absent(
        self,
        event: PlatformEvent,
        *,
        processing_state: BusProcessingState,
        owner_service: str | None,
        deadline_at: datetime | None,
    ) -> bool:
        delivery: JsonObject | None = None
        if event.delivery is not None:
            delivery = require_json_object(
                event.delivery.model_dump(mode="json"),
                "PlatformEvent.delivery",
            )
        now = utcnow()
        row = PlatformEventLog(
            event_id=event.event_id,
            type=event.type,
            company_id=event.company_id,
            payload=event.payload,
            meta=require_json_object(event.meta.model_dump(mode="json"), "PlatformEvent.meta"),
            delivery=delivery,
            processing_state=processing_state.value,
            owner_service=owner_service,
            causation_id=event.meta.causation_id,
            deadline_at=deadline_at,
            created_at=now,
            updated_at=now,
        )
        try:
            _ = await PlatformEventLog.create_platform_event_log(row)
        except IntegrityError:
            return False
        return True

    async def _event(self, event_id: str) -> PlatformEvent | None:
        row = await PlatformEventLog.get(event_id)
        if row is None:
            return None
        return row.platform_event()

    async def _set_processing_state(self, event_id: str, processing_state: BusProcessingState) -> None:
        row = await PlatformEventLog.get(event_id)
        if row is None:
            raise ValueError(f"platform_event_log row {event_id} not found")
        row.processing_state = processing_state.value
        row.updated_at = utcnow()
        _ = await row.save()

    async def _expired_commands(self, *, now: datetime, limit: int) -> list[PlatformEvent]:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        rows = await PlatformEventLog.expired_command_logs(now=now, limit=limit)
        return [row.platform_event() for row in rows]

    async def _has_terminal(self, causation_id: str) -> bool:
        return await PlatformEventLog.terminal_event_logs(causation_id).first() is not None

    async def _terminal(self, causation_id: str) -> PlatformEvent | None:
        row = await PlatformEventLog.terminal_event_logs(causation_id).order_by("-created_at").first()
        if row is None:
            return None
        return row.platform_event()

    async def _dispatch_command(self, event: PlatformEvent) -> None:
        owner = owner_service_for_event_type(event.type)
        await self._set_processing_state(event.event_id, BusProcessingState.DISPATCHED)
        client = ServiceClient()
        path = f"/{owner}/api/internal/realtime/command"
        try:
            _ = await client.post(
                owner,
                path,
                json=event.model_dump(mode="json"),
                timeout=float(get_settings().realtime.command_deadline_seconds),
            )
        except ServiceClientError as exc:
            if exc.status_code is not None and 400 <= exc.status_code < 500:
                failed = _owner_failed_event(event, exc)
                _ = await self.ingest(failed)
                await self._set_processing_state(event.event_id, BusProcessingState.FAILED)
                return
            logger.error(
                "realtime.command.dispatch_failed",
                event_id=event.event_id,
                owner=owner,
                status_code=exc.status_code,
            )
            raise

    async def _publish_to_centrifugo(self, event: PlatformEvent) -> None:
        if event.delivery is None or is_command_event_type(event.type):
            return
        frame = require_json_object(
            event.model_dump(mode="json", exclude={"delivery"}),
            "PlatformEvent.ws_frame",
        )
        for channel in centrifugo_channels_for_delivery(event.delivery):
            await centrifugo_publish(channel, frame)

    async def _maybe_offline_push(self, event: PlatformEvent) -> None:
        if event.delivery is None or event.delivery.user_ids is None:
            return
        if not event.type.startswith("notify/"):
            return
        payload = event.payload
        if not isinstance(payload, dict):
            raise ValueError(f"notify payload must be object, got {type(payload).__name__}")
        title = payload.get("title")
        message = payload.get("message")
        if not isinstance(title, str) or not title:
            raise ValueError("notify payload.title is required")
        if not isinstance(message, str) or not message:
            raise ValueError("notify payload.message is required")
        action_url = payload.get("action_url")
        if action_url is not None and not isinstance(action_url, str):
            raise ValueError("notify payload.action_url must be string or null")
        kind = payload.get("kind")
        if not isinstance(kind, str) or not kind:
            raise ValueError("notify payload.kind is required")
        data_raw = payload.get("data")
        data: JsonObject = {}
        if data_raw is not None:
            data = require_json_object(data_raw, "notify payload.data")
        priority = payload.get("priority")
        if not isinstance(priority, str) or not priority:
            raise ValueError("notify payload.priority is required")
        for user_id in event.delivery.user_ids:
            snapshot = await centrifugo_presence_stats(user_channel(user_id))
            if snapshot.connected:
                continue
            _ = await deliver_offline_push(
                user_id,
                title=title,
                message=message,
                action_url=action_url,
                tag=kind,
                priority=priority,
                data=data,
            )


async def _xadd_platform_event(event: PlatformEvent) -> None:
    settings = get_settings()
    client = events_redis_client()
    added_id = await client.xadd(
        PLATFORM_EVENTS_STREAM,
        {"event": event.model_dump_json()},
        maxlen=settings.events.stream_maxlen,
        approximate=True,
    )
    if not isinstance(added_id, str) or not added_id:
        raise RuntimeError(f"XADD platform:events failed for {event.event_id}")
    logger.debug(
        "platform_event.xadd",
        event_type=event.type,
        event_id=event.event_id,
        company_id=event.company_id,
    )


def _deadline_failed_event(command: PlatformEvent) -> PlatformEvent:
    failed_type = command.type[: -len("_requested")] + "_failed"
    actor_user_id = command.meta.actor_user_id
    if actor_user_id is None or not actor_user_id:
        raise ValueError(f"command {command.event_id} missing meta.actor_user_id for deadline fail")
    return PlatformEvent(
        type=failed_type,
        company_id=command.company_id,
        payload={
            "error_code": _TERMINAL_FAILED_DETAIL,
            "error_detail": "Command deadline exceeded before owner produced a terminal event",
        },
        meta=PlatformEventMeta(
            source="system",
            actor_user_id=actor_user_id,
            causation_id=command.event_id,
            correlation_id=command.meta.correlation_id,
            trace_id=command.meta.trace_id,
            request_id=command.meta.request_id,
        ),
        delivery=EventDelivery(user_ids=[actor_user_id]),
    )


def _owner_failed_event(command: PlatformEvent, error: ServiceClientError) -> PlatformEvent:
    failed_type = command.type[: -len("_requested")] + "_failed"
    actor_user_id = command.meta.actor_user_id
    if actor_user_id is None or not actor_user_id:
        raise ValueError(f"command {command.event_id} missing meta.actor_user_id")
    detail = error.response_text if error.response_text else str(error)
    return PlatformEvent(
        type=failed_type,
        company_id=command.company_id,
        payload={
            "error_code": "owner_rejected",
            "error_detail": detail,
        },
        meta=PlatformEventMeta(
            source="system",
            actor_user_id=actor_user_id,
            causation_id=command.event_id,
            correlation_id=command.meta.correlation_id,
            trace_id=command.meta.trace_id,
            request_id=command.meta.request_id,
        ),
        delivery=EventDelivery(user_ids=[actor_user_id]),
    )
