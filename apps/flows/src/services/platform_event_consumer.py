"""Consumer group `flows` шины `platform:events`.

Единственный durable-потребитель шины во flows (запускается фоновой задачей
в `flows_worker`). На каждое событие:

1. **Employee routing** — wake-up flow-сотрудников:
   - `worktracker/work_item/assigned` c employee-исполнителями;
   - `sync/message/created` в DIRECT-канале или с @mention employee-получателя.
2. **Триггеры `platform_event`** — matcher подписок
   (`dispatch_platform_event_triggers`).

Ошибка одного маршрута/триггера логируется и не блокирует остальные;
запись ACK'ается после обработки (poison-события не зацикливают группу).
"""

from __future__ import annotations

from pydantic import ValidationError

from apps.flows.src.container_contracts import FlowRuntimeContainer
from apps.flows.src.events import FLOWS_HITL_TURN_APPENDED
from apps.flows.src.services.employee_inbox_service import EmployeeInboxService
from apps.flows.src.triggers.handlers.platform_event import (
    dispatch_platform_event_triggers,
)
from core.events import PlatformEvent, PlatformEventGroupConsumer
from core.identity.flow_employee import is_flow_employee_user_id
from core.logging import get_logger
from core.types import JsonObject, require_json_object
from core.worktracker.events import (
    WORK_ITEM_ASSIGNED,
    WORK_ITEM_COMPLETED,
    WorkItemAssignedEventPayload,
    WorkItemEventPayload,
)
from core.worktracker.models import UsersAssignment, WorkItemHookEvent, WorkItemResolution

logger = get_logger(__name__)

# side-effect: регистрация flows UI-типов в каталоге процесса
_ = FLOWS_HITL_TURN_APPENDED

FLOWS_PLATFORM_EVENTS_GROUP = "flows"

SYNC_MESSAGE_CREATED = "sync/message/created"


def _sync_message_text(payload: JsonObject) -> str:
    """Первый text/plain блок сообщения; для медиа-сообщений — заглушка."""
    contents_raw = payload.get("contents")
    if isinstance(contents_raw, list):
        for content_raw in contents_raw:
            if not isinstance(content_raw, dict):
                continue
            if content_raw.get("type") != "text/plain":
                continue
            content_data = content_raw.get("data")
            if isinstance(content_data, dict):
                body = content_data.get("body")
                if isinstance(body, str) and body:
                    return body
    return "Новое сообщение"


def _require_str(payload: JsonObject, key: str, *, context: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{context}: field {key!r} must be a non-empty string")
    return value


class PlatformEventConsumerService:
    """Обработчик событий шины для flows: employee routing + триггеры."""

    def __init__(
        self,
        *,
        container: FlowRuntimeContainer,
        employee_inbox_service: EmployeeInboxService,
    ) -> None:
        self._container: FlowRuntimeContainer = container
        self._employee_inbox: EmployeeInboxService = employee_inbox_service

    def build_group_consumer(self, *, consumer_name: str) -> PlatformEventGroupConsumer:
        return PlatformEventGroupConsumer(
            group=FLOWS_PLATFORM_EVENTS_GROUP,
            consumer_name=consumer_name,
            on_event=self.handle_event,
        )

    async def handle_event(self, event: PlatformEvent) -> None:
        if event.type == WORK_ITEM_ASSIGNED:
            await self._route_work_item_assigned(event)
        elif event.type == SYNC_MESSAGE_CREATED:
            await self._route_sync_message_created(event)
        elif event.type == WORK_ITEM_COMPLETED:
            await self._route_work_item_completed(event)
        fired = await dispatch_platform_event_triggers(
            container=self._container,
            event=event,
        )
        if fired:
            logger.info(
                "platform_event.triggers_fired",
                event_type=event.type,
                event_id=event.event_id,
                fired=fired,
            )

    async def _route_work_item_assigned(self, event: PlatformEvent) -> None:
        """Назначение задачи flow-сотруднику → employee inbox."""
        try:
            payload = WorkItemAssignedEventPayload.model_validate(event.payload)
        except ValidationError as exc:
            logger.error(
                "platform_event.work_item_assigned_payload_invalid",
                event_id=event.event_id,
                error=str(exc),
            )
            return
        item = payload.work_item
        if not isinstance(item.assignment, UsersAssignment):
            return
        employee_user_ids = [
            user_id
            for user_id in item.assignment.user_ids
            if is_flow_employee_user_id(user_id)
        ]
        if not employee_user_ids:
            return
        text = item.title if not item.description else f"{item.title}\n\n{item.description}"
        for employee_user_id in employee_user_ids:
            try:
                _ = await self._employee_inbox.dispatch_work_item_assigned(
                    company_id=item.company_id,
                    employee_user_id=employee_user_id,
                    sender_user_id=payload.assigned_by_user_id,
                    work_item_id=item.work_item_id,
                    text=text,
                )
            except Exception as exc:
                logger.error(
                    "platform_event.employee_work_item_dispatch_failed",
                    work_item_id=item.work_item_id,
                    employee_user_id=employee_user_id,
                    error=str(exc),
                    exc_info=True,
                )

    async def _route_sync_message_created(self, event: PlatformEvent) -> None:
        """DM или @mention flow-сотрудника в sync → employee inbox."""
        payload = require_json_object(event.payload, "sync/message/created payload")
        recipient_user_ids_raw = payload.get("recipient_user_ids")
        if not isinstance(recipient_user_ids_raw, list):
            return
        recipient_user_ids = [uid for uid in recipient_user_ids_raw if isinstance(uid, str)]
        employee_recipient_ids = [
            uid for uid in recipient_user_ids if is_flow_employee_user_id(uid)
        ]
        if not employee_recipient_ids:
            return

        channel_type = payload.get("channel_type")
        mentioned_raw = payload.get("mentioned_user_ids")
        mentioned: set[str] = set()
        if isinstance(mentioned_raw, list):
            mentioned = {uid for uid in mentioned_raw if isinstance(uid, str)}
        is_direct = channel_type == "direct"

        sender = require_json_object(
            payload.get("sender"), "sync/message/created sender"
        )
        sender_user_id = _require_str(sender, "user_id", context="sync sender")
        channel_id = _require_str(payload, "channel_id", context="sync/message/created")
        message_id = _require_str(payload, "message_id", context="sync/message/created")
        text = _sync_message_text(payload)

        for employee_user_id in employee_recipient_ids:
            if employee_user_id == sender_user_id:
                continue
            if not (is_direct or employee_user_id in mentioned):
                continue
            try:
                _ = await self._employee_inbox.dispatch_sync_message(
                    company_id=event.company_id,
                    employee_user_id=employee_user_id,
                    sender_user_id=sender_user_id,
                    channel_id=channel_id,
                    message_id=message_id,
                    text=text,
                )
            except Exception as exc:
                logger.error(
                    "platform_event.employee_sync_dispatch_failed",
                    channel_id=channel_id,
                    employee_user_id=employee_user_id,
                    error=str(exc),
                    exc_info=True,
                )

    async def _route_work_item_completed(self, event: PlatformEvent) -> None:
        """HITL resume: completed WorkItem с binding в hooks → durable resume."""
        try:
            payload = WorkItemEventPayload.model_validate(event.payload)
        except ValidationError as exc:
            logger.error(
                "platform_event.work_item_completed_payload_invalid",
                event_id=event.event_id,
                error=str(exc),
            )
            return
        item = payload.work_item
        completed_hooks = item.hooks_for(WorkItemHookEvent.COMPLETED)
        if not completed_hooks:
            return
        resolution = item.resolution if item.resolution is not None else WorkItemResolution()
        for hook in completed_hooks:
            if not hook.binding:
                continue
            try:
                await self._container.hitl_work_item_service.resume_from_completion(
                    work_item_id=item.work_item_id,
                    binding=hook.binding,
                    resolution=resolution,
                    company_id=item.company_id,
                )
            except Exception as exc:
                logger.error(
                    "platform_event.hitl_resume_failed",
                    work_item_id=item.work_item_id,
                    event_id=event.event_id,
                    error=str(exc),
                    exc_info=True,
                )


__all__ = ["FLOWS_PLATFORM_EVENTS_GROUP", "PlatformEventConsumerService"]
