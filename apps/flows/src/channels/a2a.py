"""
A2AChannel — реализация A2A Protocol 1.0 (protobuf / a2a-sdk 1.x).
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncGenerator
from typing import override

from a2a.helpers.proto_helpers import get_message_text, new_data_part, new_text_part
from a2a.types import (
    Artifact,
    CancelTaskRequest,
    DeleteTaskPushNotificationConfigRequest,
    GetTaskPushNotificationConfigRequest,
    GetTaskRequest,
    ListTaskPushNotificationConfigsRequest,
    ListTaskPushNotificationConfigsResponse,
    ListTasksRequest,
    ListTasksResponse,
    Message,
    Part,
    Role,
    SendMessageRequest,
    SubscribeToTaskRequest,
    Task,
    TaskArtifactUpdateEvent,
    TaskPushNotificationConfig,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)

from apps.flows.config import get_settings as get_flows_settings
from apps.flows.src.channels.base import BaseChannel
from apps.flows.src.channels.types import ChannelRequestContext, PreparedTaskParams
from apps.flows.src.container_contracts import FlowRuntimeContainer
from apps.flows.src.files import (
    extract_incoming_a2a_files,
    format_a2a_files_content,
    transcribe_incoming_audio_files,
)
from apps.flows.src.files.ssrf_fetch import fetch_public_url_bytes
from apps.flows.src.state.cancellation import CANCEL_KEY_TTL
from apps.flows.src.streaming import Emitter
from apps.flows.src.streaming.base import StreamEvent
from apps.flows.src.streaming.subscriber import EventSubscriber
from apps.flows.src.utils import extract_json_from_response
from apps.idle_worker.tasks.task_names import TASK_SEND_TASK_UPDATE
from core.a2a import (
    get_part_text,
    is_terminal_a2a_task_state,
    make_task_status,
    mapping_from_struct,
    part_has_text,
)
from core.config.testing import is_testing
from core.context import require_context, set_current_channel
from core.files.create_spec import FileCreateSpec, FilePostCreate, FileSourceKind, FileSourceRef
from core.files.file_ref import FileRef, file_id_from_download_url
from core.files.registry import default_retention_for_source
from core.logging import get_logger
from core.state import ExecutionState
from core.tasks import enqueue
from core.tasks.push_notifications import (
    delete_push_config,
    get_push_config,
    list_push_configs,
    set_push_config,
)
from core.types import JsonObject
from core.worktracker.models import build_conversation_ref

logger = get_logger(__name__)


def _task_needs_live_subscribe_tail(task: Task) -> bool:
    """True — после snapshot нужен live Redis tail (задача ещё не terminal)."""
    if not task.HasField("status"):
        return True
    return not is_terminal_a2a_task_state(task.status.state)


def _text_part(text: str) -> Part:
    return new_text_part(text)


def _data_part(data: JsonObject) -> Part:
    return new_data_part(data)


def _part_text(part: Part) -> str | None:
    if not part_has_text(part):
        return None
    return get_part_text(part)


def _agent_text_message(text: str) -> Message:
    return Message(
        message_id=str(uuid.uuid4()),
        role=Role.ROLE_AGENT,
        parts=[_text_part(text)],
    )


def _message_metadata(params: SendMessageRequest) -> JsonObject | None:
    if not params.HasField("metadata"):
        return None
    return mapping_from_struct(params.metadata)


def _branch_id_from_message_metadata(metadata: JsonObject | None) -> str:
    if not metadata:
        return "default"
    branch = metadata.get("branch")
    if branch is None:
        return "default"
    if not isinstance(branch, str) or not branch.strip():
        raise ValueError("a2a.message.metadata.branch must be a non-empty string")
    return branch.strip()


def _should_return_immediately(params: SendMessageRequest) -> bool:
    """A2A 1.0: SendMessageConfiguration.return_immediately (default false = blocking)."""
    if not params.HasField("configuration"):
        return False
    return bool(params.configuration.return_immediately)


async def _build_task_from_events(
    events: list[StreamEvent],
    task_id: str,
    context_id: str,
    input_message: Message,
    flow_id: str,
    container: FlowRuntimeContainer | None = None,
) -> Task:
    """Строит Task из накопленных A2A 1.0 событий."""
    artifacts_dict: dict[str, Artifact] = {}
    final_status: TaskStatus | None = None
    response_parts: list[str] = []
    reasoning_parts: list[str] = []

    for event in events:
        if isinstance(event, TaskArtifactUpdateEvent):
            if event.HasField("artifact"):
                artifact_name = event.artifact.name or "response"
                for part in event.artifact.parts:
                    text = _part_text(part)
                    if text is not None:
                        if artifact_name == "reasoning":
                            if event.append:
                                reasoning_parts.append(text)
                            else:
                                reasoning_parts = [text]
                        elif artifact_name == "response":
                            if event.append:
                                response_parts.append(text)
                            else:
                                response_parts = [text]
        else:
            task_state = event.status.state
            if task_state == TaskState.TASK_STATE_INPUT_REQUIRED:
                final_status = event.status
            elif is_terminal_a2a_task_state(task_state):
                final_status = event.status

    response_text = "".join(response_parts)
    if (
        not response_text
        and final_status is not None
        and final_status.HasField("message")
        and final_status.message.parts
    ):
        status_message_parts: list[str] = []
        for part in final_status.message.parts:
            text = _part_text(part)
            if text is not None:
                status_message_parts.append(text)
        response_text = "".join(status_message_parts)

    if reasoning_parts:
        reasoning_text = "".join(reasoning_parts)
        artifacts_dict["reasoning"] = Artifact(
            artifact_id=str(uuid.uuid4()),
            name="reasoning",
            parts=[_text_part(reasoning_text)],
        )

    json_data = extract_json_from_response(response_text)

    if json_data is not None:
        artifacts_dict["response"] = Artifact(
            artifact_id=str(uuid.uuid4()),
            name="response",
            parts=[_data_part({"res": json.dumps(json_data, ensure_ascii=False)})],
        )
    elif response_text and reasoning_parts:
        artifacts_dict["response"] = Artifact(
            artifact_id=str(uuid.uuid4()),
            name="response",
            parts=[_text_part(response_text)],
        )

    artifacts = list(artifacts_dict.values())

    if final_status is None:
        raise ValueError(
            f"A2A stream for task {task_id!r} ended without a terminal TaskStatusUpdateEvent"
        )

    session_id = f"{flow_id}:{context_id}"
    existing_history: list[Message] = []
    if container is not None:
        state = await container.workflow_runtime.get_state(session_id)
        existing_history = list(state.messages) if state else []

    history_message = Message()
    history_message.CopyFrom(input_message)
    history_message.task_id = task_id

    for msg in existing_history:
        if not msg.task_id:
            msg.task_id = task_id

    history: list[Message] = [*existing_history, history_message]

    if response_text and final_status.state == TaskState.TASK_STATE_COMPLETED:
        agent_message = _agent_text_message(response_text)
        agent_message.task_id = task_id
        history.append(agent_message)
    elif (
        final_status.state == TaskState.TASK_STATE_INPUT_REQUIRED
        and final_status.HasField("message")
    ):
        agent_message = Message()
        agent_message.CopyFrom(final_status.message)
        if not agent_message.task_id:
            agent_message.task_id = task_id
        history.append(agent_message)

    if (
        artifacts
        and final_status.HasField("message")
        and final_status.state
        not in (
            TaskState.TASK_STATE_INPUT_REQUIRED,
            TaskState.TASK_STATE_FAILED,
            TaskState.TASK_STATE_CANCELED,
        )
    ):
        cleared = make_task_status(final_status.state)
        if final_status.HasField("timestamp"):
            cleared.timestamp.CopyFrom(final_status.timestamp)
        final_status = cleared

    task = Task(
        id=task_id,
        context_id=context_id,
        status=final_status,
    )
    if artifacts:
        task.artifacts.extend(artifacts)
    task.history.extend(history)
    return task


class A2AChannel(BaseChannel):
    """A2A канал коммуникации (Protocol 1.0)."""

    name: str = "a2a"

    @override
    async def send_to_user(
        self,
        content: str,
        buttons: list[str] | None = None,
        attachments: list[JsonObject] | None = None,
    ) -> None:
        _ = buttons, attachments
        if not self.context:
            logger.warning("Cannot send_to_user: no context available")
            return

        task_id = self.context.metadata.get("task_id")
        if not isinstance(task_id, str) or not task_id:
            raise ValueError("A2AChannel.send_to_user requires context.metadata.task_id")
        context_id = self.context.metadata.get("context_id")
        if not isinstance(context_id, str) or not context_id:
            raise ValueError("A2AChannel.send_to_user requires context.metadata.context_id")
        session_id = self._generate_session_id(context_id)

        exec_state = ExecutionState(
            task_id=task_id,
            context_id=context_id,
            session_id=session_id,
            user_id=self.context.user.user_id,
            user_groups=self._get_user_groups_from_context(self.context),
        )
        emitter = Emitter(self.container.redis_client, exec_state)
        await emitter.emit_text(content, append=False, last_chunk=True)

    async def _handle_takeover_user_reply(
        self,
        prepared: PreparedTaskParams,
    ) -> AsyncGenerator[TaskStatusUpdateEvent, None]:
        if self.context is None or self.context.active_company is None:
            raise ValueError("A2A takeover reply requires active_company in context")
        company_id = self.context.active_company.company_id

        work_item_id = prepared.takeover_work_item_id
        if work_item_id is None:
            raise ValueError("takeover_work_item_id is required for takeover user reply")

        item = await self.container.work_item_service.get(company_id, work_item_id)
        ref = build_conversation_ref(item)
        if ref is None:
            raise ValueError(f"WorkItem {work_item_id!r} без ссылки на разговор сессии")
        source_message_id = (
            prepared.message.message_id
            if prepared.message is not None
            else f"{work_item_id}:{prepared.task_id}"
        )
        _ = await self.container.hitl_conversation_service.append_user_message(
            company_id=company_id,
            work_item_id=work_item_id,
            ref=ref,
            user_id=prepared.user_id,
            text=prepared.content,
            source_message_id=source_message_id,
        )
        logger.info(
            "[on_message_stream] takeover user-reply appended to session log, "
            + "task_id=%s, work_item=%s",
            prepared.task_id,
            work_item_id,
        )
        yield TaskStatusUpdateEvent(
            task_id=prepared.task_id,
            context_id=prepared.context_id,
            status=make_task_status(
                TaskState.TASK_STATE_INPUT_REQUIRED,
                message=_agent_text_message(prepared.content),
            ),
        )

    async def _persist_incoming_a2a_files(self, message: Message) -> tuple[list[FileRef], str]:
        """Part.raw → S3; Part.url platform download → file_id; external url → SSRF-safe fetch."""
        incoming = extract_incoming_a2a_files(message)
        if not incoming:
            return [], ""

        if not self.context or not self.context.active_company:
            raise ValueError(
                "Загрузка вложений A2A требует active_company в контексте запроса"
            )

        company_id = self.context.active_company.company_id
        files_data: list[FileRef] = []

        context_id = message.context_id.strip()
        if not context_id:
            raise ValueError("A2A Part.raw/url требует message.context_id для FLOW_SESSION")
        session_id = f"{self.flow_id}:{context_id}"

        for inc in incoming:
            data = inc.data
            content_type = inc.content_type
            if data is None:
                if not inc.uri:
                    raise ValueError("Part.url без uri")
                linked_file_id = file_id_from_download_url(inc.uri)
                if linked_file_id:
                    record = await self.container.files_service.get_optional(linked_file_id)
                    if record is None:
                        raise ValueError(f"Part.url с неизвестным file_id: {linked_file_id}")
                    if record.company_id != company_id:
                        raise ValueError("Part.url file_id не принадлежит активной компании")
                    files_data.append(
                        FileRef(
                            file_id=record.file_id,
                            original_name=record.original_name,
                            url=record.download_url if record.download_url is not None else inc.uri,
                            content_type=record.content_type,
                            file_size=record.file_size,
                            checksum=record.checksum,
                            is_public=record.is_public,
                        )
                    )
                    continue
                # External URL: SSRF-safe fetch in channel persist path.
                data, fetched_ct = await fetch_public_url_bytes(inc.uri)
                if content_type is None or not content_type.strip():
                    content_type = fetched_ct

            if not content_type or not content_type.strip():
                raise ValueError("Part.raw/url content_type (media_type) обязателен для state.files")
            spec = FileCreateSpec(
                source_kind=FileSourceKind.FLOW_SESSION,
                source_ref=FileSourceRef(
                    session_id=session_id,
                    flow_id=self.flow_id,
                ),
                retention=default_retention_for_source(FileSourceKind.FLOW_SESSION),
                post_create=FilePostCreate(is_public=False),
            )
            record = await self.container.files_service.create(
                spec=spec,
                data=data,
                original_name=inc.original_name,
                content_type=content_type.strip(),
            )
            files_data.append(FileRef.from_record(record))

        return files_data, format_a2a_files_content(files_data)

    async def _transcribe_incoming_audio(self, files_data: list[FileRef]) -> str:
        if not self.context or not self.context.active_company:
            raise ValueError(
                "Авто-STT входящих audio-вложений требует active_company в контексте запроса"
            )
        return await transcribe_incoming_audio_files(
            container=self.container,
            files_data=files_data,
            company_id=self.context.active_company.company_id,
        )

    async def _prepare_a2a_params(
        self, params: SendMessageRequest, metadata: JsonObject | None = None
    ) -> PreparedTaskParams:
        message = params.message
        content = get_message_text(message)

        files_data, files_content_suffix = await self._persist_incoming_a2a_files(message)
        if files_data:
            audio_transcript_suffix = await self._transcribe_incoming_audio(files_data)
            if audio_transcript_suffix:
                content += audio_transcript_suffix
        if files_content_suffix:
            content += files_content_suffix

        prepared = await self._prepare_task_params(
            content=content,
            context_id=message.context_id or None,
            task_id=message.task_id or None,
            message=message,
            metadata=metadata if metadata is not None else _message_metadata(params),
            files_data=files_data,
        )
        return prepared

    async def _register_push_from_send_configuration(
        self,
        params: SendMessageRequest,
        *,
        task_id: str,
    ) -> None:
        """A2A 1.0: configuration.task_push_notification_config до старта task."""
        if not params.HasField("configuration"):
            return
        configuration = params.configuration
        if not configuration.HasField("task_push_notification_config"):
            return
        push_cfg = TaskPushNotificationConfig()
        push_cfg.CopyFrom(configuration.task_push_notification_config)
        push_cfg.task_id = task_id
        if not push_cfg.url.strip():
            raise ValueError("SendMessageConfiguration.task_push_notification_config.url is required")
        _ = await set_push_config(push_cfg)

    @override
    async def on_message_send(
        self, params: SendMessageRequest, context: ChannelRequestContext = None
    ) -> Task | Message:
        set_current_channel(self)

        metadata = _message_metadata(params)
        branch_for_perm = _branch_id_from_message_metadata(metadata)
        await self.check_permissions(self._get_user_groups_from_context(context), branch_for_perm)

        prepared = await self._prepare_a2a_params(params, metadata)
        await self._register_push_from_send_configuration(params, task_id=prepared.task_id)

        if prepared.is_takeover_user_reply:
            events: list[StreamEvent] = [
                event async for event in self._handle_takeover_user_reply(prepared)
            ]
            if prepared.message is None:
                raise ValueError("A2A prepared params must include original message")
            return await _build_task_from_events(
                events=events,
                task_id=prepared.task_id,
                context_id=prepared.context_id,
                input_message=prepared.message,
                flow_id=self.flow_id,
                container=self.container,
            )

        if _should_return_immediately(params):
            await self.create_task(prepared)
            task = Task(
                id=prepared.task_id,
                context_id=prepared.context_id,
                status=make_task_status(
                    TaskState.TASK_STATE_SUBMITTED,
                    message=_agent_text_message("Task submitted"),
                ),
            )
            if prepared.message is not None:
                task.history.append(prepared.message)
            return task

        timeout = 120.0 if is_testing() else 300.0
        subscriber = EventSubscriber(self.container.redis_client)
        ready_event = asyncio.Event()

        async def collect_with_subscription() -> list[StreamEvent]:
            return await subscriber.collect(
                prepared.task_id, timeout=timeout, ready_event=ready_event
            )

        collect_task = asyncio.create_task(collect_with_subscription())
        _ = await ready_event.wait()

        logger.debug(f"[A2A] Subscribed to stream:{prepared.task_id}, kicking task")
        await self.create_task(prepared)
        events = await collect_task

        logger.debug(f"[A2A] Collected {len(events)} events for task {prepared.task_id}")
        if prepared.message is None:
            raise ValueError("A2A prepared params must include original message")

        return await _build_task_from_events(
            events=events,
            task_id=prepared.task_id,
            context_id=prepared.context_id,
            input_message=prepared.message,
            flow_id=self.flow_id,
            container=self.container,
        )

    @override
    async def on_message_stream(
        self, params: SendMessageRequest, context: ChannelRequestContext = None
    ) -> AsyncGenerator[Message | Task | TaskStatusUpdateEvent | TaskArtifactUpdateEvent, None]:
        set_current_channel(self)

        metadata = _message_metadata(params)
        branch_for_perm = _branch_id_from_message_metadata(metadata)
        await self.check_permissions(self._get_user_groups_from_context(context), branch_for_perm)

        prepared = await self._prepare_a2a_params(params, metadata)
        await self._register_push_from_send_configuration(params, task_id=prepared.task_id)

        if prepared.is_takeover_user_reply:
            async for event in self._handle_takeover_user_reply(prepared):
                yield event
            return

        logger.info(
            f"[on_message_stream] Prepared task_id={prepared.task_id}, subscribing to Redis..."
        )
        subscriber = EventSubscriber(self.container.redis_client)
        event_queue: asyncio.Queue[StreamEvent | None] = asyncio.Queue()
        ready_event = asyncio.Event()

        async def collect_events() -> None:
            async for event in subscriber.subscribe(prepared.task_id, ready_event=ready_event):
                await event_queue.put(event)
            await event_queue.put(None)

        collect_task = asyncio.create_task(collect_events())

        logger.info("[on_message_stream] Waiting for Redis subscription to be ready...")
        _ = await ready_event.wait()
        logger.info("[on_message_stream] Redis subscription ready, creating task...")

        await self.create_task(prepared)

        while True:
            event = await event_queue.get()
            if event is None:
                break
            yield event

        await collect_task

    @override
    async def on_get_task(
        self, params: GetTaskRequest, context: ChannelRequestContext = None
    ) -> Task | None:
        _ = context
        task = await self._get_task_from_state(params.id)
        if task is None:
            return None
        if params.history_length and task.history:
            # protobuf repeated: truncate in place via slice copy
            kept = list(task.history)[-params.history_length :]
            del task.history[:]
            task.history.extend(kept)
        return task

    @override
    async def on_cancel_task(
        self, params: CancelTaskRequest, context: ChannelRequestContext = None
    ) -> Task | None:
        _ = context
        logger.info(f"Cancel task: {params.id}")

        _ = await self.container.redis_client.set(f"cancel:{params.id}", "1", ttl=CANCEL_KEY_TTL)

        task = await self._cancel_task_in_state(params.id)

        if task:
            _ = await enqueue(
                TASK_SEND_TASK_UPDATE,
                task.id,
                task.context_id,
                "canceled",
                "Task cancelled",
                True,
                background_kind="a2a_task",
            )

        return task

    @override
    async def on_subscribe_to_task(
        self, params: SubscribeToTaskRequest, context: ChannelRequestContext = None
    ) -> AsyncGenerator[Message | Task | TaskStatusUpdateEvent | TaskArtifactUpdateEvent, None]:
        """Snapshot Task + живой tail Redis `stream:{task_id}` до финального события."""
        _ = context
        set_current_channel(self)
        task = await self.on_get_task(GetTaskRequest(id=params.id))
        if task is None:
            return
        yield task
        if not _task_needs_live_subscribe_tail(task):
            return

        timeout = (
            120.0 if is_testing() else float(get_flows_settings().default_flow_timeout_seconds)
        )
        subscriber = EventSubscriber(self.container.redis_client)
        logger.info(
            "a2a.subscribe.live_tail",
            task_id=task.id,
            task_state=task.status.state if task.HasField("status") else None,
            timeout_seconds=timeout,
        )
        async for event in subscriber.subscribe(task.id, timeout=timeout):
            yield event

    @override
    async def on_list_tasks(
        self, params: ListTasksRequest, context: ChannelRequestContext = None
    ) -> ListTasksResponse:
        """ListTasks: сессии flow, видимые текущему user/company (search_sessions)."""
        _ = context
        ctx = require_context()
        user_id = ctx.user.user_id
        if not user_id:
            raise ValueError("ListTasks requires authenticated user")

        offset = 0
        if params.page_token.strip():
            try:
                offset = int(params.page_token.strip())
            except ValueError as exc:
                raise ValueError("Invalid ListTasks page_token") from exc
            if offset < 0:
                raise ValueError("page_token must be >= 0")

        page_size = params.page_size if params.page_size > 0 else 50
        if page_size > 200:
            page_size = 200

        sessions, total = await self.container.workflow_runtime.search_sessions(
            user_id=user_id,
            flow_id=self.flow_id,
            limit=page_size,
            offset=offset,
        )

        # next_page_token REQUIRED в A2A 1.0 (пустая строка = конец списка)
        response = ListTasksResponse(
            page_size=page_size,
            total_size=total,
            next_page_token="",
        )
        for session in sessions:
            context_id = session.context_id
            if not context_id:
                continue
            if params.context_id and context_id != params.context_id:
                continue
            task = await self._get_task_from_state(context_id)
            if task is None:
                continue
            if params.status and task.HasField("status") and task.status.state != params.status:
                continue
            if not params.include_artifacts and task.artifacts:
                del task.artifacts[:]
            if params.history_length and task.history:
                kept = list(task.history)[-params.history_length :]
                del task.history[:]
                task.history.extend(kept)
            response.tasks.append(task)

        next_offset = offset + page_size
        if next_offset < total:
            response.next_page_token = str(next_offset)
        return response

    @override
    async def on_create_task_push_notification_config(
        self, params: TaskPushNotificationConfig, context: ChannelRequestContext = None
    ) -> TaskPushNotificationConfig:
        _ = context
        config = await set_push_config(params)
        logger.info(f"Set push notification config for task: {params.task_id}")
        return config

    @override
    async def on_get_task_push_notification_config(
        self,
        params: GetTaskPushNotificationConfigRequest,
        context: ChannelRequestContext = None,
    ) -> TaskPushNotificationConfig | None:
        _ = context
        config = await get_push_config(params)
        logger.info(f"Get push notification config for task: {params.task_id}")
        return config

    @override
    async def on_list_task_push_notification_configs(
        self,
        params: ListTaskPushNotificationConfigsRequest,
        context: ChannelRequestContext = None,
    ) -> ListTaskPushNotificationConfigsResponse:
        _ = context
        result = await list_push_configs(params)
        logger.info(
            "List push notification configs for task: %s, found: %s",
            params.task_id,
            len(result.configs),
        )
        return result

    @override
    async def on_delete_task_push_notification_config(
        self,
        params: DeleteTaskPushNotificationConfigRequest,
        context: ChannelRequestContext = None,
    ) -> None:
        _ = context
        await delete_push_config(params)
        logger.info(
            f"Deleted push notification config: {params.id} for task: {params.task_id}"
        )
