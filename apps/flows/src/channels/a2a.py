"""
A2AChannel — реализация A2A Protocol 1.0 (protobuf / a2a-sdk 1.x).
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncGenerator
from typing import override

from a2a.helpers.proto_helpers import get_message_text
from a2a.types import (
    CancelTaskRequest,
    DeleteTaskPushNotificationConfigRequest,
    GetTaskPushNotificationConfigRequest,
    GetTaskRequest,
    ListTaskPushNotificationConfigsRequest,
    ListTaskPushNotificationConfigsResponse,
    ListTasksRequest,
    ListTasksResponse,
    Message,
    SendMessageRequest,
    SubscribeToTaskRequest,
    Task,
    TaskArtifactUpdateEvent,
    TaskPushNotificationConfig,
    TaskStatusUpdateEvent,
)

from apps.flows.config import get_settings as get_flows_settings
from apps.flows.src.a2a.share_task_redaction import (
    artifact_event_for_share_viewer,
    task_for_share_viewer,
)
from apps.flows.src.a2a.task_projection_service import A2ATaskProjectionService
from apps.flows.src.channels.base import BaseChannel
from apps.flows.src.channels.types import ChannelRequestContext, PreparedTaskParams
from apps.flows.src.contracts import (
    ChannelRegistryProtocol,
    FlowFactoryProtocol,
    ToolRegistryProtocol,
)
from apps.flows.src.durable_execution import DurableWorkflowRuntime
from apps.flows.src.files import (
    extract_incoming_a2a_files,
    format_a2a_files_content,
    transcribe_incoming_audio_files,
)
from apps.flows.src.files.ssrf_fetch import fetch_public_url_bytes
from apps.flows.src.models.a2a_projection import A2ATaskEvent, A2ATaskProjection
from apps.flows.src.models.flow_config import FlowConfig
from apps.flows.src.services.flow_ui_share_service import FlowUIShareService
from apps.flows.src.services.handoff_orchestrator_service import HandoffOrchestratorService
from apps.flows.src.services.hitl_conversation_service import HitlConversationService
from apps.flows.src.state.cancellation import CANCEL_KEY_TTL
from apps.flows.src.streaming import Emitter
from apps.flows.src.streaming.base import StreamEvent
from apps.flows.src.streaming.subscriber import EventSubscriber, event_platform_sequence
from apps.idle_worker.tasks.task_names import TASK_SEND_TASK_UPDATE
from core.a2a import (
    is_interrupted_a2a_task_state,
    is_terminal_a2a_task_state,
    mapping_from_struct,
    struct_from_mapping,
)
from core.authz.service import AuthzService
from core.clients.redis_client import RedisClient
from core.config.testing import is_testing
from core.context import require_context, set_current_channel
from core.db.storage import Storage
from core.files.create_spec import FileCreateSpec, FilePostCreate, FileSourceKind, FileSourceRef
from core.files.file_ref import FileRef, file_id_from_download_url, stored_file_ref
from core.files.registry import default_retention_for_source
from core.files.service import FilesService
from core.flow_ui.action import ui_action_from_message
from core.flow_ui.projection import assert_fields_outside_redacted
from core.logging import get_logger
from core.mail.service import MailService
from core.models.context_models import Context
from core.models.flow_ui_share import FlowUIShareGrant
from core.state import ExecutionState
from core.state.interrupt import OperatorTaskInterrupt
from core.tasks import enqueue
from core.tasks.push_notifications import (
    delete_push_config,
    get_push_config,
    list_push_configs,
    set_push_config,
)
from core.types import JsonObject
from core.variables.service import VariablesService
from core.worktracker.models import WorkItem, build_conversation_ref

logger = get_logger(__name__)


def _task_needs_live_subscribe_tail(task: Task) -> bool:
    """True — после snapshot нужен live Redis tail (задача ещё не terminal)."""
    if not task.HasField("status"):
        return True
    return not is_terminal_a2a_task_state(task.status.state)


def _a2a_projection_is_parked(task: Task) -> bool:
    """SendMessage / SendStreamingMessage: проекция уже terminal или interrupted."""
    if not task.HasField("status"):
        return False
    state = task.status.state
    return is_terminal_a2a_task_state(state) or is_interrupted_a2a_task_state(state)


def _projection_fingerprint(task: Task) -> tuple[int, int, str, str]:
    state = int(task.status.state) if task.HasField("status") else -1
    history_len = len(task.history)
    last_history_id = task.history[-1].message_id if task.history else ""
    status_message_id = ""
    if task.HasField("status") and task.status.HasField("message"):
        status_message_id = task.status.message.message_id
    return (state, history_len, last_history_id, status_message_id)


def _this_send_finished_in_process(prior: Task | None, current: Task) -> bool:
    """Pub/Sub already dropped: return durable row only if THIS send parked it."""
    if not _a2a_projection_is_parked(current):
        return False
    if prior is None:
        return True
    if not _a2a_projection_is_parked(prior):
        return True
    return _projection_fingerprint(prior) != _projection_fingerprint(current)


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


def _stream_event_for_share_viewer(
    event: StreamEvent, grant: FlowUIShareGrant | None
) -> StreamEvent:
    if isinstance(event, TaskArtifactUpdateEvent):
        return artifact_event_for_share_viewer(event, grant)
    return event


def _should_return_immediately(params: SendMessageRequest) -> bool:
    """A2A 1.0: SendMessageConfiguration.return_immediately (default false = blocking)."""
    if not params.HasField("configuration"):
        return False
    return bool(params.configuration.return_immediately)


class A2AChannel(BaseChannel):
    """A2A канал коммуникации (Protocol 1.0)."""

    name: str = "a2a"

    def __init__(
        self,
        flow_id: str,
        context: Context | None = None,
        flow_config: FlowConfig | None = None,
        *,
        variables_service: VariablesService,
        authz_service: AuthzService,
        workflow_runtime: DurableWorkflowRuntime,
        redis_client: RedisClient,
        handoff_orchestrator_service: HandoffOrchestratorService,
        flow_factory: FlowFactoryProtocol,
        tool_registry: ToolRegistryProtocol,
        projection_service: A2ATaskProjectionService,
        shared_storage: Storage,
        channel_registry: ChannelRegistryProtocol,
        mail_service: MailService,
        flow_ui_share_service: FlowUIShareService,
        hitl_conversation_service: HitlConversationService,
        files_service: FilesService,
    ) -> None:
        super().__init__(
            flow_id,
            context=context,
            flow_config=flow_config,
            variables_service=variables_service,
            authz_service=authz_service,
            workflow_runtime=workflow_runtime,
            redis_client=redis_client,
            handoff_orchestrator_service=handoff_orchestrator_service,
            flow_factory=flow_factory,
            tool_registry=tool_registry,
            projection_service=projection_service,
            shared_storage=shared_storage,
            channel_registry=channel_registry,
            mail_service=mail_service,
        )
        self._flow_ui_share_service: FlowUIShareService = flow_ui_share_service
        self._hitl_conversation_service: HitlConversationService = hitl_conversation_service
        self._files_service: FilesService = files_service

    def _share_grant_id(self) -> str | None:
        raw = self.context.metadata.get("flow_ui_share_grant_id") if self.context else None
        return raw if isinstance(raw, str) and raw else None

    async def _authorize_share(
        self,
        *,
        context_id: str,
        require_editor: bool,
    ) -> FlowUIShareGrant | None:
        grant_id = self._share_grant_id()
        if grant_id is None:
            return None
        if self.context is None or self.context.active_company is None:
            raise PermissionError("Flow UI share requires an active company")
        return await self._flow_ui_share_service.authorize(
            grant_id=grant_id,
            company_id=self.context.active_company.company_id,
            flow_id=self.flow_id,
            context_id=context_id,
            require_editor=require_editor,
        )

    async def _authorize_message_or_permissions(
        self,
        params: SendMessageRequest,
        context: ChannelRequestContext,
        metadata: JsonObject | None,
    ) -> FlowUIShareGrant | None:
        _ = context
        grant_id = self._share_grant_id()
        if grant_id is None:
            await self.check_permissions(
                require_context().user.user_id,
                _branch_id_from_message_metadata(metadata),
            )
            return None
        # Любое сообщение продолжает чужую сессию — нужен editor grant на её context_id.
        context_id = params.message.context_id.strip()
        if not context_id:
            raise PermissionError("Shared sessions require message.context_id")
        return await self._authorize_share(context_id=context_id, require_editor=True)

    def _task_access_scope(self) -> tuple[str, str]:
        context = require_context()
        if context.active_company is None:
            raise ValueError("A2A task access requires active_company")
        user_id = context.user.user_id
        if user_id.strip() == "":
            raise ValueError("A2A task access requires authenticated user")
        return context.active_company.company_id, user_id

    async def _operator_task_interrupt_state(
        self, *, company_id: str, context_id: str
    ) -> ExecutionState | None:
        state = await self._workflow_runtime.get_state(
            self._generate_session_id(context_id),
            company_id=company_id,
        )
        if state is None:
            return None
        if state.interrupt is None or not isinstance(
            state.interrupt.body, OperatorTaskInterrupt
        ):
            return None
        return state

    async def _load_hitl_parked_task(self, *, company_id: str, task_id: str) -> Task | None:
        """Company-scoped Task when the session is parked on OperatorTaskInterrupt.

        Owner filter would hide the customer's parked task from a queue member
        opening the WorkItem card. Share grants keep their own context path.
        """
        task = await A2ATaskProjection.get_task(
            company_id=company_id,
            task_id=task_id,
        )
        if task is None:
            return None
        scoped = await A2ATaskProjection.get_task_for_context(
            company_id=company_id,
            flow_id=self.flow_id,
            context_id=task.context_id,
            task_id=task_id,
        )
        if scoped is None:
            return None
        parked = await self._operator_task_interrupt_state(
            company_id=company_id,
            context_id=scoped.context_id,
        )
        if parked is None:
            return None
        return scoped

    async def _load_projected_task(self, task_id: str) -> Task | None:
        company_id, owner_user_id = self._task_access_scope()
        share_context = (
            self.context.metadata.get("flow_ui_share_context_id")
            if self.context is not None
            else None
        )
        if self._share_grant_id() is not None:
            if not isinstance(share_context, str) or not share_context:
                raise PermissionError("Flow UI share token has no context scope")
            grant = await self._authorize_share(
                context_id=share_context,
                require_editor=False,
            )
            task = await A2ATaskProjection.get_task_for_context(
                company_id=company_id,
                flow_id=self.flow_id,
                context_id=share_context,
                task_id=task_id,
            )
        else:
            grant = None
            task = await A2ATaskProjection.get_task_for_owner(
                company_id=company_id,
                owner_user_id=owner_user_id,
                task_id=task_id,
            )
            if task is None:
                task = await self._load_hitl_parked_task(
                    company_id=company_id,
                    task_id=task_id,
                )
        if task is None:
            return None
        return task_for_share_viewer(task, grant)

    async def _projected_task(self, task_id: str) -> Task:
        task = await self._load_projected_task(task_id)
        if task is None:
            raise RuntimeError(f"Durable A2A Task {task_id!r} was not materialized")
        return task

    async def _prior_projection(self, task_id: str) -> Task | None:
        return await self._load_projected_task(task_id)

    async def _submitted_task_snapshot(
        self, task_id: str, *, grant: FlowUIShareGrant | None
    ) -> Task:
        """Sequence-0 Task хода (SUBMITTED, history, без артефактов) для первого кадра стрима.

        Доступ уже проверен ``_projected_task``; здесь только чтение ledger в scope компании.
        """
        company_id, _ = self._task_access_scope()
        snapshot = await A2ATaskEvent.get_submitted_task(
            company_id=company_id,
            task_id=task_id,
        )
        if snapshot is None:
            raise RuntimeError(f"Durable A2A Task {task_id!r} has no submitted snapshot")
        return task_for_share_viewer(snapshot, grant)

    async def _share_grant_for_context(self, context_id: str) -> FlowUIShareGrant | None:
        if self._share_grant_id() is None:
            return None
        return await self._authorize_share(context_id=context_id, require_editor=False)

    async def _latest_sequence(self, task_id: str) -> int:
        company_id, _ = self._task_access_scope()
        return await A2ATaskProjection.get_latest_sequence(
            company_id=company_id,
            task_id=task_id,
        )

    async def _replay_durable_stream_events(
        self, task_id: str, *, grant: FlowUIShareGrant | None, after_sequence: int = 0
    ) -> AsyncGenerator[StreamEvent, None]:
        """Yield lossless status/artifact updates from the durable A2A ledger."""
        company_id, _ = self._task_access_scope()
        stored_events = await A2ATaskProjection.list_events_after_sequence(
            company_id=company_id,
            task_id=task_id,
            after_sequence=after_sequence,
        )
        for stored in stored_events:
            yield _stream_event_for_share_viewer(stored.event, grant)

    @override
    async def send_to_user(
        self,
        content: str,
        buttons: list[str] | None = None,
        attachments: list[JsonObject] | None = None,
    ) -> None:
        _ = buttons, attachments
        if not self.context:
            logger.warning("flows.cannot.send_to_user.context.available")
            return

        task_id = self.context.metadata.get("task_id")
        if not isinstance(task_id, str) or not task_id:
            raise ValueError("A2AChannel.send_to_user requires context.metadata.task_id")
        context_id = self.context.metadata.get("context_id")
        if not isinstance(context_id, str) or not context_id:
            raise ValueError("A2AChannel.send_to_user requires context.metadata.context_id")
        session_id = self._generate_session_id(context_id)

        exec_state = ExecutionState.model_validate(
            {
                "task_id": task_id,
                "context_id": context_id,
                "session_id": session_id,
                "user_id": self.context.user.user_id,
                "user_groups": self._get_user_groups_from_context(self.context),
            }
        )
        emitter = Emitter.open(self._projection_service, exec_state)
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

        item = await WorkItem.require_in_company(company_id, work_item_id)
        ref = build_conversation_ref(item)
        if ref is None:
            raise ValueError(f"WorkItem {work_item_id!r} without a session conversation reference")
        source_message_id = (
            prepared.message.message_id
            if prepared.message is not None
            else f"{work_item_id}:{prepared.task_id}"
        )
        _ = await self._hitl_conversation_service.append_user_message(
            company_id=company_id,
            work_item_id=work_item_id,
            ref=ref,
            user_id=prepared.user_id,
            text=prepared.content,
            source_message_id=source_message_id,
        )
        logger.info("flows.on_message_stream.takeover.user.reply.appended", task_id=prepared.task_id, work_item=work_item_id)
        parked_task_id = ref.a2a_task_id
        if not isinstance(parked_task_id, str) or parked_task_id.strip() == "":
            raise ValueError(f"WorkItem {work_item_id!r} without a2a_task_id for takeover reply")
        parked_state = await self._operator_task_interrupt_state(
            company_id=company_id,
            context_id=ref.context_id,
        )
        if parked_state is None:
            raise ValueError("takeover user reply requires parked OperatorTaskInterrupt")
        interrupt = parked_state.interrupt
        if interrupt is None:
            raise ValueError("takeover user reply requires parked OperatorTaskInterrupt")
        if parked_state.task_id != parked_task_id:
            parked_state = parked_state.model_copy(update={"task_id": parked_task_id})
        emitter = await Emitter.create_ensured(self._projection_service, parked_state)
        await emitter.emit_interrupt(interrupt)
        parked_task = await self._projected_task(parked_task_id)
        if not parked_task.HasField("status"):
            raise ValueError("takeover user reply requires parked task status")
        event = TaskStatusUpdateEvent(
            task_id=parked_task.id,
            context_id=parked_task.context_id,
            status=parked_task.status,
        )
        if parked_task.HasField("metadata"):
            event.metadata.CopyFrom(parked_task.metadata)
        yield event

    async def _persist_incoming_a2a_files(self, message: Message) -> tuple[list[FileRef], str]:
        """Part.raw → S3; Part.url platform download → file_id; external url → SSRF-safe fetch."""
        incoming = extract_incoming_a2a_files(message)
        if not incoming:
            return [], ""

        if not self.context or not self.context.active_company:
            raise ValueError(
                "A2A attachment upload requires active_company in the request context"
            )

        company_id = self.context.active_company.company_id
        files_data: list[FileRef] = []

        context_id = message.context_id.strip()
        if not context_id:
            raise ValueError("A2A Part.raw/url requires message.context_id for FLOW_SESSION")
        session_id = f"{self.flow_id}:{context_id}"

        for inc in incoming:
            data = inc.data
            content_type = inc.content_type
            if data is None:
                if not inc.uri:
                    raise ValueError("Part.url has no uri")
                linked_file_id = file_id_from_download_url(inc.uri)
                if linked_file_id:
                    record = await self._files_service.get_optional(linked_file_id)
                    if record is None:
                        raise ValueError(f"Part.url with unknown file_id: {linked_file_id}")
                    if record.company_id != company_id:
                        raise ValueError("Part.url file_id does not belong to the active company")
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
                raise ValueError("Part.raw/url content_type (media_type) is required for state.files")
            spec = FileCreateSpec(
                source_kind=FileSourceKind.FLOW_SESSION,
                source_ref=FileSourceRef(
                    session_id=session_id,
                    flow_id=self.flow_id,
                ),
                retention=default_retention_for_source(FileSourceKind.FLOW_SESSION),
                post_create=FilePostCreate(is_public=False),
            )
            record = await self._files_service.create(
                spec=spec,
                data=data,
                original_name=inc.original_name,
                content_type=content_type.strip(),
            )
            files_data.append(stored_file_ref(record))

        return files_data, format_a2a_files_content(files_data)

    async def _transcribe_incoming_audio(self, files_data: list[FileRef]) -> str:
        if not self.context or not self.context.active_company:
            raise ValueError(
                "Auto-STT of incoming audio attachments requires active_company in the request context"
            )
        return await transcribe_incoming_audio_files(
            files_service=self._files_service,
            files_data=files_data,
            company_id=self.context.active_company.company_id,
        )

    async def _prepare_a2a_params(
        self,
        params: SendMessageRequest,
        metadata: JsonObject | None,
        share_grant: FlowUIShareGrant | None,
    ) -> PreparedTaskParams:
        message = params.message
        content = get_message_text(message)
        ui_action = ui_action_from_message(message)
        if ui_action is not None and share_grant is not None:
            assert_fields_outside_redacted(ui_action.fields, share_grant.redacted_paths)

        files_data, files_content_suffix = await self._persist_incoming_a2a_files(message)
        if files_data:
            audio_transcript_suffix = await self._transcribe_incoming_audio(files_data)
            if audio_transcript_suffix:
                content += audio_transcript_suffix
        if files_content_suffix:
            content += files_content_suffix

        return await self._prepare_task_params(
            content=content,
            context_id=message.context_id or None,
            task_id=message.task_id or None,
            message=message,
            metadata=metadata,
            files_data=files_data,
            ui_action=ui_action,
            share_grant=share_grant,
        )

    async def _register_push_from_send_configuration(
        self,
        params: SendMessageRequest,
        *,
        task_id: str,
    ) -> None:
        """A2A 1.0: configuration.task_push_notification_config до старта task."""
        if self._share_grant_id() is not None:
            if params.HasField("configuration") and params.configuration.HasField(
                "task_push_notification_config"
            ):
                raise PermissionError("Shared sessions cannot register push endpoints")
            return
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
        grant = await self._authorize_message_or_permissions(params, context, metadata)

        prepared = await self._prepare_a2a_params(params, metadata, grant)
        await self._register_push_from_send_configuration(params, task_id=prepared.task_id)

        if prepared.is_takeover_user_reply:
            closing: TaskStatusUpdateEvent | None = None
            async for event in self._handle_takeover_user_reply(prepared):
                closing = event
            if closing is None:
                raise RuntimeError("takeover user reply produced no status event")
            return await self._projected_task(closing.task_id)

        if _should_return_immediately(params):
            await self.create_task(prepared)
            return await self._projected_task(prepared.task_id)

        prior = await self._prior_projection(prepared.task_id)
        timeout = 120.0 if is_testing() else 300.0
        subscriber = EventSubscriber(self._redis_client)
        ready_event = asyncio.Event()

        async def collect_with_subscription() -> list[StreamEvent]:
            return await subscriber.collect(
                prepared.task_id, timeout=timeout, ready_event=ready_event
            )

        collect_task = asyncio.create_task(collect_with_subscription())
        _ = await ready_event.wait()

        logger.debug("flows.a2a.stream_subscribed", task_id=prepared.task_id)
        await self.create_task(prepared)
        projected = await self._projected_task(prepared.task_id)
        if _this_send_finished_in_process(prior, projected):
            # In-process enqueue (sync_tools) finishes while collect is blocked
            # off the event loop: Pub/Sub drops, collect waits until pytest timeout.
            # Durable projection is the source of truth — only for THIS send.
            _ = collect_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await collect_task
            return projected

        events = await collect_task
        logger.debug("flows.a2a.events_collected", task_id=prepared.task_id, count=len(events))
        _ = events
        return await self._projected_task(prepared.task_id)

    @override
    async def on_message_stream(
        self, params: SendMessageRequest, context: ChannelRequestContext = None
    ) -> AsyncGenerator[Message | Task | TaskStatusUpdateEvent | TaskArtifactUpdateEvent, None]:
        set_current_channel(self)

        metadata = _message_metadata(params)
        grant = await self._authorize_message_or_permissions(params, context, metadata)

        prepared = await self._prepare_a2a_params(params, metadata, grant)
        await self._register_push_from_send_configuration(params, task_id=prepared.task_id)

        if prepared.is_takeover_user_reply:
            async for event in self._handle_takeover_user_reply(prepared):
                yield event
            return
        share_grant = await self._share_grant_for_context(prepared.context_id)

        logger.info("flows.a2a.stream_subscribe", task_id=prepared.task_id)
        # A2A 1.0: первый кадр SendStreamingMessage — сам Task, дальше только события с
        # sequence > snapshot. Новый Task: snapshot sequence 0 (SUBMITTED, history с сообщением
        # пользователя, без артефактов). Возобновляемый Task (resume после interrupt): прежняя
        # проекция и события только этого хода. Так клиент собирает Task без дублей независимо
        # от того, успел ли worker опубликовать события до отправки snapshot.
        prior = await self._prior_projection(prepared.task_id)
        snapshot_sequence = (
            0 if prior is None else await self._latest_sequence(prepared.task_id)
        )
        subscriber = EventSubscriber(self._redis_client)
        event_queue: asyncio.Queue[StreamEvent | None] = asyncio.Queue()
        ready_event = asyncio.Event()

        async def collect_events() -> None:
            async for event in subscriber.subscribe(
                prepared.task_id,
                ready_event=ready_event,
                after_sequence=snapshot_sequence,
            ):
                await event_queue.put(event)
            await event_queue.put(None)

        collect_task = asyncio.create_task(collect_events())
        try:
            logger.info("flows.on_message_stream.waiting.redis.subscription.ready")
            _ = await ready_event.wait()
            logger.info("flows.on_message_stream.redis.subscription.ready.creating")

            await self.create_task(prepared)
            projected = await self._projected_task(prepared.task_id)
            yield (
                prior
                if prior is not None
                else await self._submitted_task_snapshot(prepared.task_id, grant=share_grant)
            )
            if _this_send_finished_in_process(prior, projected):
                # In-process enqueue (sync_tools) finishes before the live
                # listener reads Redis: Pub/Sub is not a queue and drops.
                # Durable ledger is the source of truth — same as SendMessage.
                _ = collect_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await collect_task
                async for event in self._replay_durable_stream_events(
                    prepared.task_id,
                    grant=share_grant,
                    after_sequence=snapshot_sequence,
                ):
                    yield event
                return

            while True:
                event = await event_queue.get()
                if event is None:
                    break
                yield _stream_event_for_share_viewer(event, share_grant)
            await collect_task
        finally:
            if not collect_task.done():
                _ = collect_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await collect_task

    @override
    async def on_get_task(
        self, params: GetTaskRequest, context: ChannelRequestContext = None
    ) -> Task | None:
        _ = context
        company_id, owner_user_id = self._task_access_scope()
        share_context = (
            self.context.metadata.get("flow_ui_share_context_id")
            if self.context is not None
            else None
        )
        if self._share_grant_id() is not None:
            if not isinstance(share_context, str) or not share_context:
                raise PermissionError("Flow UI share token has no context scope")
            grant = await self._authorize_share(
                context_id=share_context,
                require_editor=False,
            )
            task = await A2ATaskProjection.get_task_for_context(
                company_id=company_id,
                flow_id=self.flow_id,
                context_id=share_context,
                task_id=params.id,
            )
            # GetTask/CancelTask id may be context_id (same contract as
            # BaseChannel._resolve_session_id_for_a2a_lookup).
            if task is None and params.id == share_context:
                shared_tasks, _ = await A2ATaskProjection.list_tasks_for_context(
                    company_id=company_id,
                    flow_id=self.flow_id,
                    context_id=share_context,
                    task_state=None,
                    limit=1,
                    offset=0,
                )
                task = shared_tasks[0] if shared_tasks else None
        else:
            grant = None
            task = await A2ATaskProjection.get_task_for_owner(
                company_id=company_id,
                owner_user_id=owner_user_id,
                task_id=params.id,
            )
            if task is None:
                task = await A2ATaskProjection.get_latest_for_context(
                    company_id=company_id,
                    owner_user_id=owner_user_id,
                    flow_id=self.flow_id,
                    context_id=params.id,
                )
            if task is None:
                task = await self._load_hitl_parked_task(
                    company_id=company_id,
                    task_id=params.id,
                )
        if task is None:
            return None
        if params.history_length and task.history:
            # protobuf repeated: truncate in place via slice copy
            kept = list(task.history)[-params.history_length :]
            del task.history[:]
            task.history.extend(kept)
        return task_for_share_viewer(task, grant)

    @override
    async def on_cancel_task(
        self, params: CancelTaskRequest, context: ChannelRequestContext = None
    ) -> Task | None:
        _ = context
        logger.info("flows.a2a.task_cancel", task_id=params.id)

        accessible = await self.on_get_task(GetTaskRequest(id=params.id))
        if accessible is None:
            return None
        if self._share_grant_id() is not None:
            _ = await self._authorize_share(
                context_id=accessible.context_id,
                require_editor=True,
            )

        # Worker CancellationToken keys by task_id; params.id may be context_id.
        cancel_task_id = accessible.id
        _ = await self._redis_client.set(
            f"cancel:{cancel_task_id}", "1", ttl=CANCEL_KEY_TTL
        )

        task = await self._cancel_task_in_state(cancel_task_id)

        if task:
            company_id, _ = self._task_access_scope()
            cancel_event = TaskStatusUpdateEvent(
                task_id=task.id,
                context_id=task.context_id,
                status=task.status,
            )
            cancel_event.metadata.CopyFrom(
                struct_from_mapping(
                    {"platformEventId": f"terminal:{task.id}:canceled"}
                )
            )
            _ = await self._projection_service.publish(
                company_id=company_id,
                event=cancel_event,
            )
            _ = await enqueue(
                TASK_SEND_TASK_UPDATE,
                task.id,
                task.context_id,
                "canceled",
                "Task cancelled",
                True,
                background_kind="a2a_task",
            )

            return await self._projected_task(task.id)
        return None

    @override
    async def on_subscribe_to_task(
        self,
        params: SubscribeToTaskRequest,
        context: ChannelRequestContext = None,
    ) -> AsyncGenerator[Message | Task | TaskStatusUpdateEvent | TaskArtifactUpdateEvent, None]:
        """Snapshot Task (sequence S), then live Redis tail of events with sequence > S.

        Подписка на Redis открывается до чтения snapshot: между snapshot и хвостом нет окна
        потери, а события с sequence <= S уже учтены в snapshot и не отдаются повторно —
        клиент собирает Task из snapshot и хвоста без дублей частей артефактов.
        """
        _ = context
        set_current_channel(self)
        task = await self.on_get_task(GetTaskRequest(id=params.id))
        if task is None:
            return
        if not _task_needs_live_subscribe_tail(task):
            yield task
            return

        grant = await self._share_grant_for_context(task.context_id)
        company_id, _ = self._task_access_scope()
        timeout = (
            120.0 if is_testing() else float(get_flows_settings().default_flow_timeout_seconds)
        )
        subscriber = EventSubscriber(self._redis_client)
        event_queue: asyncio.Queue[StreamEvent | None] = asyncio.Queue()
        ready_event = asyncio.Event()

        async def collect_events() -> None:
            async for event in subscriber.subscribe(
                task.id, timeout=timeout, ready_event=ready_event
            ):
                await event_queue.put(event)
            await event_queue.put(None)

        collect_task = asyncio.create_task(collect_events())
        try:
            _ = await ready_event.wait()
            snapshot, snapshot_sequence = (
                await A2ATaskProjection.get_task_with_sequence(
                    company_id=company_id,
                    task_id=task.id,
                )
            )
            yield task_for_share_viewer(snapshot, grant)
            if not _task_needs_live_subscribe_tail(snapshot):
                return
            logger.info(
                "a2a.subscribe.live_tail",
                task_id=task.id,
                task_state=snapshot.status.state if snapshot.HasField("status") else None,
                live_after_sequence=snapshot_sequence,
                timeout_seconds=timeout,
            )
            while True:
                event = await event_queue.get()
                if event is None:
                    break
                sequence = event_platform_sequence(event)
                if sequence is not None and sequence <= snapshot_sequence:
                    continue
                yield _stream_event_for_share_viewer(event, grant)
        finally:
            if not collect_task.done():
                _ = collect_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await collect_task

    @override
    async def on_list_tasks(
        self, params: ListTasksRequest, context: ChannelRequestContext = None
    ) -> ListTasksResponse:
        """ListTasks from the durable lossless query projection."""
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

        if ctx.active_company is None:
            raise ValueError("ListTasks requires active_company")
        share_context = ctx.metadata.get("flow_ui_share_context_id")
        share_grant: FlowUIShareGrant | None = None
        if self._share_grant_id() is not None:
            if not isinstance(share_context, str) or not share_context:
                raise PermissionError("Flow UI share token has no context scope")
            if params.context_id and params.context_id != share_context:
                raise PermissionError("ListTasks context is outside the share grant")
            share_grant = await self._authorize_share(
                context_id=share_context,
                require_editor=False,
            )
            tasks, total = await A2ATaskProjection.list_tasks_for_context(
                company_id=ctx.active_company.company_id,
                flow_id=self.flow_id,
                context_id=share_context,
                task_state=int(params.status) if params.status else None,
                limit=page_size,
                offset=offset,
            )
        else:
            tasks, total = await A2ATaskProjection.list_tasks(
                company_id=ctx.active_company.company_id,
                owner_user_id=user_id,
                flow_id=self.flow_id,
                context_id=params.context_id or None,
                task_state=int(params.status) if params.status else None,
                limit=page_size,
                offset=offset,
            )
            context_id = params.context_id.strip() if params.context_id else ""
            if total == 0 and context_id:
                parked = await self._operator_task_interrupt_state(
                    company_id=ctx.active_company.company_id,
                    context_id=context_id,
                )
                if parked is not None:
                    tasks, total = (
                        await A2ATaskProjection.list_tasks_for_context(
                            company_id=ctx.active_company.company_id,
                            flow_id=self.flow_id,
                            context_id=context_id,
                            task_state=int(params.status) if params.status else None,
                            limit=page_size,
                            offset=offset,
                        )
                    )

        # next_page_token REQUIRED в A2A 1.0 (пустая строка = конец списка)
        response = ListTasksResponse(
            page_size=page_size,
            total_size=total,
            next_page_token="",
        )
        for task in tasks:
            if not params.include_artifacts and task.artifacts:
                del task.artifacts[:]
            if params.history_length and task.history:
                kept = list(task.history)[-params.history_length :]
                del task.history[:]
                task.history.extend(kept)
            response.tasks.append(task_for_share_viewer(task, share_grant))

        next_offset = offset + len(tasks)
        if next_offset < total:
            response.next_page_token = str(next_offset)
        return response

    @override
    async def on_create_task_push_notification_config(
        self, params: TaskPushNotificationConfig, context: ChannelRequestContext = None
    ) -> TaskPushNotificationConfig:
        _ = context
        if self._share_grant_id() is not None:
            raise PermissionError("Shared sessions cannot manage push endpoints")
        config = await set_push_config(params)
        logger.info("flows.a2a.push_config_set", task_id=params.task_id)
        return config

    @override
    async def on_get_task_push_notification_config(
        self,
        params: GetTaskPushNotificationConfigRequest,
        context: ChannelRequestContext = None,
    ) -> TaskPushNotificationConfig | None:
        _ = context
        if self._share_grant_id() is not None:
            raise PermissionError("Shared sessions cannot manage push endpoints")
        config = await get_push_config(params)
        logger.info("flows.a2a.push_config_get", task_id=params.task_id)
        return config

    @override
    async def on_list_task_push_notification_configs(
        self,
        params: ListTaskPushNotificationConfigsRequest,
        context: ChannelRequestContext = None,
    ) -> ListTaskPushNotificationConfigsResponse:
        _ = context
        if self._share_grant_id() is not None:
            raise PermissionError("Shared sessions cannot manage push endpoints")
        result = await list_push_configs(params)
        logger.info("flows.list.push.notification.configs.task", task_id=params.task_id, configs_count=len(result.configs))
        return result

    @override
    async def on_delete_task_push_notification_config(
        self,
        params: DeleteTaskPushNotificationConfigRequest,
        context: ChannelRequestContext = None,
    ) -> None:
        _ = context
        if self._share_grant_id() is not None:
            raise PermissionError("Shared sessions cannot manage push endpoints")
        await delete_push_config(params)
        logger.info(
            "flows.a2a.push_config_deleted",
            config_id=params.id,
            task_id=params.task_id,
        )
