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

from apps.flows.src.durable_execution import DurableWorkflowRuntime
from apps.flows.src.events import FLOWS_HITL_TURN_APPENDED
from apps.flows.src.services.employee_inbox_service import EmployeeInboxService
from apps.flows.src.services.hitl_work_item_service import HitlWorkItemService
from apps.flows.src.triggers.handlers.platform_event import (
    dispatch_platform_event_triggers,
)
from core.authz.service import AuthzService
from core.clients.redis_client import RedisClient
from core.events import PlatformEvent, PlatformEventGroupConsumer
from core.files.file_ref import FileRef
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

_SYNC_FILE_CONTENT_TYPES = frozenset(
    {"file/image", "file/document", "file/audio", "file/video"}
)


def _file_ref_from_attachment(data: JsonObject, *, context: str) -> FileRef:
    file_id = data.get("file_id")
    original_name = data.get("original_name")
    content_type = data.get("content_type")
    file_size = data.get("file_size")
    if not isinstance(file_id, str) or file_id == "":
        raise ValueError(f"{context}: file_id must be a non-empty string")
    if not isinstance(original_name, str) or original_name == "":
        raise ValueError(f"{context}: original_name must be a non-empty string")
    if not isinstance(content_type, str) or content_type == "":
        raise ValueError(f"{context}: content_type must be a non-empty string")
    if isinstance(file_size, bool) or not isinstance(file_size, int) or file_size < 0:
        raise ValueError(f"{context}: file_size must be a non-negative integer")
    return FileRef(
        file_id=file_id,
        original_name=original_name,
        content_type=content_type,
        file_size=file_size,
    )


def _sync_message_files(payload: JsonObject) -> list[FileRef]:
    """Вложения file/* сообщения. Отбор по типу делает граф сотрудника."""
    contents_raw = payload.get("contents")
    if contents_raw is None:
        return []
    if not isinstance(contents_raw, list):
        raise TypeError("sync/message/created contents must be a list")
    refs: list[FileRef] = []
    for index, content_raw in enumerate(contents_raw):
        if not isinstance(content_raw, dict):
            raise TypeError(f"sync/message/created contents[{index}] must be an object")
        if content_raw.get("type") not in _SYNC_FILE_CONTENT_TYPES:
            continue
        data = content_raw.get("data")
        if not isinstance(data, dict):
            raise TypeError(f"sync/message/created contents[{index}].data must be an object")
        refs.append(
            _file_ref_from_attachment(data, context=f"sync/message/created contents[{index}]")
        )
    return refs


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
        redis_client: RedisClient,
        workflow_runtime: DurableWorkflowRuntime,
        authz_service: AuthzService,
        hitl_work_item_service: HitlWorkItemService,
        employee_inbox_service: EmployeeInboxService,
    ) -> None:
        self._redis_client: RedisClient = redis_client
        self._workflow_runtime: DurableWorkflowRuntime = workflow_runtime
        self._authz_service: AuthzService = authz_service
        self._hitl_work_item_service: HitlWorkItemService = hitl_work_item_service
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
            redis_client=self._redis_client,
            workflow_runtime=self._workflow_runtime,
            authz_service=self._authz_service,
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
                    files=_sync_message_files(payload),
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
                await self._hitl_work_item_service.resume_from_completion(
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
