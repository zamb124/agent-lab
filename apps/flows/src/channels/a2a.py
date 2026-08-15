"""
A2AChannel — реализация A2A Protocol 1.0 (protobuf / a2a-sdk 1.x).
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections.abc import AsyncGenerator
from typing import override

from a2a.helpers.proto_helpers import get_message_text, new_text_part
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
    Part,
    Role,
    SendMessageRequest,
    SubscribeToTaskRequest,
    Task,
    TaskArtifactUpdateEvent,
    TaskPushNotificationConfig,
    TaskState,
    TaskStatusUpdateEvent,
)

from apps.flows.config import get_settings as get_flows_settings
from apps.flows.src.a2a.interaction_parser import (
    FlowUIIngressKind,
    parse_flow_ui_command,
)
from apps.flows.src.a2a.negotiation import A2ARepresentationSelector
from apps.flows.src.a2a.share_task_redaction import task_with_share_redaction
from apps.flows.src.channels.base import BaseChannel
from apps.flows.src.channels.types import ChannelRequestContext, PreparedTaskParams
from apps.flows.src.container_contracts import FlowRuntimeContainer
from apps.flows.src.files import (
    extract_incoming_a2a_files,
    format_a2a_files_content,
    transcribe_incoming_audio_files,
)
from apps.flows.src.files.ssrf_fetch import fetch_public_url_bytes
from apps.flows.src.models.flow_config import FlowConfig
from apps.flows.src.state.cancellation import CANCEL_KEY_TTL
from apps.flows.src.streaming import Emitter
from apps.flows.src.streaming.base import StreamEvent
from apps.flows.src.streaming.subscriber import EventSubscriber
from apps.idle_worker.tasks.task_names import TASK_SEND_TASK_UPDATE
from core.a2a import (
    A2ARepresentation,
    is_interrupted_a2a_task_state,
    is_terminal_a2a_task_state,
    make_task_status,
    mapping_from_struct,
    struct_from_mapping,
)
from core.config.testing import is_testing
from core.context import Context, require_context, set_current_channel
from core.files.create_spec import FileCreateSpec, FilePostCreate, FileSourceKind, FileSourceRef
from core.files.file_ref import FileRef, file_id_from_download_url
from core.files.registry import default_retention_for_source
from core.logging import get_logger
from core.models.flow_interface import EmbedInterfaceOverride
from core.models.flow_ui_share import FlowUIShareGrant
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


def _a2a_projection_is_parked(task: Task) -> bool:
    """SendMessage / SendStreamingMessage: проекция уже terminal или interrupted."""
    if not task.HasField("status"):
        return False
    state = task.status.state
    return is_terminal_a2a_task_state(state) or is_interrupted_a2a_task_state(state)


def _text_part(text: str) -> Part:
    return new_text_part(text)


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


def _flow_ui_task_id(context_id: str, action_id: str) -> str:
    """Stable A2A Task identity for retries of one UI command."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"linnex:flow-ui:{context_id}:{action_id}"))


class A2AChannel(BaseChannel):
    """A2A канал коммуникации (Protocol 1.0)."""

    name: str = "a2a"

    def __init__(
        self,
        flow_id: str,
        context: Context | None = None,
        flow_config: FlowConfig | None = None,
        *,
        container: FlowRuntimeContainer,
        activated_extensions: tuple[str, ...] = (),
        interface_override: EmbedInterfaceOverride | None = None,
    ) -> None:
        super().__init__(
            flow_id,
            context=context,
            flow_config=flow_config,
            container=container,
            interface_override=interface_override,
        )
        self._activated_extensions: tuple[str, ...] = activated_extensions

    def _share_grant_id(self) -> str | None:
        raw = self.context.metadata.get("flow_ui_share_grant_id") if self.context else None
        return raw if isinstance(raw, str) and raw else None

    async def _authorize_share(
        self,
        *,
        context_id: str,
        document_id: str | None = None,
        require_editor: bool,
    ) -> FlowUIShareGrant | None:
        grant_id = self._share_grant_id()
        if grant_id is None:
            return None
        if self.context is None or self.context.active_company is None:
            raise PermissionError("Flow UI share requires an active company")
        return await self.container.flow_ui_share_service.authorize(
            grant_id=grant_id,
            company_id=self.context.active_company.company_id,
            flow_id=self.flow_id,
            context_id=context_id,
            document_id=document_id,
            require_editor=require_editor,
        )

    async def _task_for_share_viewer(
        self,
        task: Task,
        grant: FlowUIShareGrant | None,
    ) -> Task:
        if grant is None or not grant.redacted_value_paths:
            return task
        state = await self.container.workflow_runtime.get_state(
            f"{self.flow_id}:{task.context_id}",
            company_id=grant.company_id,
        )
        if state is None:
            raise PermissionError("Shared Flow UI session no longer exists")
        return task_with_share_redaction(
            task,
            grant=grant,
            document=state.ui_document,
            representation=state.a2a_representation,
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
        command = parse_flow_ui_command(params.message)
        if command is None:
            raise PermissionError("Shared sessions accept only Flow UI A2A commands")
        context_id = params.message.context_id.strip()
        if not context_id:
            raise PermissionError("Shared Flow UI commands require context_id")
        return await self._authorize_share(
            context_id=context_id,
            document_id=command.document_id,
            require_editor=command.kind != FlowUIIngressKind.BOOTSTRAP,
        )

    def _task_access_scope(self) -> tuple[str, str]:
        context = require_context()
        if context.active_company is None:
            raise ValueError("A2A task access requires active_company")
        user_id = context.user.user_id
        if user_id.strip() == "":
            raise ValueError("A2A task access requires authenticated user")
        return context.active_company.company_id, user_id

    async def _projected_task(self, task_id: str) -> Task:
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
            task = await self.container.a2a_task_repository.get_task_for_context(
                company_id=company_id,
                flow_id=self.flow_id,
                context_id=share_context,
                task_id=task_id,
            )
        else:
            grant = None
            task = await self.container.a2a_task_repository.get_task_for_owner(
                company_id=company_id,
                owner_user_id=owner_user_id,
                task_id=task_id,
            )
        if task is None:
            raise RuntimeError(f"Durable A2A Task {task_id!r} was not materialized")
        return await self._task_for_share_viewer(task, grant)

    async def _replay_durable_stream_events(
        self, task_id: str, *, after_sequence: int = 0
    ) -> AsyncGenerator[StreamEvent, None]:
        """Yield lossless status/artifact updates from the durable A2A ledger."""
        company_id, _ = self._task_access_scope()
        stored_events = await self.container.a2a_task_repository.list_events_after_sequence(
            company_id=company_id,
            task_id=task_id,
            after_sequence=after_sequence,
        )
        for stored in stored_events:
            yield stored.event

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

        exec_state = ExecutionState.model_validate(
            {
                "task_id": task_id,
                "context_id": context_id,
                "session_id": session_id,
                "user_id": self.context.user.user_id,
                "user_groups": self._get_user_groups_from_context(self.context),
            }
        )
        emitter = Emitter.from_container(self.container, exec_state)
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
        event = TaskStatusUpdateEvent(
            task_id=prepared.task_id,
            context_id=prepared.context_id,
            status=make_task_status(
                TaskState.TASK_STATE_INPUT_REQUIRED,
                message=_agent_text_message(prepared.content),
            ),
        )
        stored = await self.container.a2a_task_projection_service.publish(
            company_id=company_id,
            event=event,
        )
        if not isinstance(stored, TaskStatusUpdateEvent):
            raise RuntimeError("takeover status projection returned non-status event")
        yield stored

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
        flow_ui_command = parse_flow_ui_command(message)

        files_data, files_content_suffix = await self._persist_incoming_a2a_files(message)
        if files_data:
            audio_transcript_suffix = await self._transcribe_incoming_audio(files_data)
            if audio_transcript_suffix:
                content += audio_transcript_suffix
        if files_content_suffix:
            content += files_content_suffix

        representation = A2ARepresentationSelector().select(
            activated_extensions=self._activated_extensions,
            message_metadata=(
                mapping_from_struct(message.metadata)
                if message.HasField("metadata")
                else {}
            ),
            accepted_output_modes=(
                params.configuration.accepted_output_modes
                if params.HasField("configuration")
                else ()
            ),
        )
        if (
            flow_ui_command is not None
            and representation.representation != A2ARepresentation.A2UI_0_9_1
        ):
            raise ValueError(
                "Flow UI commands require activated A2UI v0.9.1 capabilities"
            )
        resolved_context_id = message.context_id or None
        resolved_task_id = message.task_id or None
        if flow_ui_command is not None:
            if resolved_context_id is None:
                raise ValueError("Flow UI commands require message.context_id")
            if resolved_task_id is None:
                resolved_task_id = _flow_ui_task_id(
                    resolved_context_id,
                    flow_ui_command.action_id,
                )

        prepared = await self._prepare_task_params(
            content=content,
            context_id=resolved_context_id,
            task_id=resolved_task_id,
            message=message,
            metadata=metadata if metadata is not None else _message_metadata(params),
            files_data=files_data,
            a2a_representation=representation,
            flow_ui_command=flow_ui_command,
        )
        return prepared

    async def _process_flow_ui_control(self, prepared: PreparedTaskParams) -> Task:
        command = prepared.flow_ui_command
        if command is None or command.kind == FlowUIIngressKind.SUBMIT:
            raise ValueError("Flow UI control handler requires bootstrap or sync")
        if self.context is None or self.context.active_company is None:
            raise ValueError("Flow UI control command requires active company context")

        service = self.container.flow_ui_session_service
        share_grant = await self._authorize_share(
            context_id=prepared.context_id,
            document_id=command.document_id,
            require_editor=command.kind != FlowUIIngressKind.BOOTSTRAP,
        )
        if command.kind == FlowUIIngressKind.BOOTSTRAP:
            initial_document = await self._initial_flow_ui_document(
                flow_id=self.flow_id,
                branch_id=prepared.branch_id,
                context_id=prepared.context_id,
            )
            result = await service.bootstrap(
                command=command,
                task_id=prepared.task_id,
                context_id=prepared.context_id,
                session_id=prepared.session_id,
                user_id=self.context.user.user_id,
                initiator_user_id=self.context.user.user_id,
                branch_id=prepared.branch_id,
                initial_document=initial_document,
                representation=prepared.a2a_representation,
                share_grant=share_grant,
            )
        else:
            result = await service.sync(
                command=command,
                task_id=prepared.task_id,
                context_id=prepared.context_id,
                session_id=prepared.session_id,
                user_id=self.context.user.user_id,
                share_grant=share_grant,
            )

        if not result.was_applied:
            try:
                return await self._projected_task(prepared.task_id)
            except RuntimeError:
                pass

        emission_state = result.state.runtime_copy()
        emission_state.task_id = prepared.task_id
        emission_state.context_id = prepared.context_id
        emission_state.session_id = prepared.session_id
        emission_state.a2a_representation = prepared.a2a_representation
        await self._ensure_a2a_task_projection(
            params=prepared,
            state=emission_state,
            company_id=self.context.active_company.company_id,
        )
        emitter = Emitter.from_container(self.container, emission_state)
        if result.transition is None:
            await emitter.emit_flow_ui_snapshot()
        else:
            await emitter.emit_flow_ui_transition(result.transition)
        await emitter.emit_complete("", has_artifact=True)
        return await self._projected_task(prepared.task_id)

    async def _apply_flow_ui_submit(self, prepared: PreparedTaskParams) -> bool:
        command = prepared.flow_ui_command
        if command is None or command.kind != FlowUIIngressKind.SUBMIT:
            return True
        if self.context is None:
            raise ValueError("Flow UI submit requires request context")
        share_grant = await self._authorize_share(
            context_id=prepared.context_id,
            document_id=command.document_id,
            require_editor=True,
        )
        result = await self.container.flow_ui_session_service.submit(
            command=command,
            task_id=prepared.task_id,
            context_id=prepared.context_id,
            session_id=prepared.session_id,
            user_id=self.context.user.user_id,
            representation=prepared.a2a_representation,
            share_grant=share_grant,
        )
        prepared.content = result.content
        # Ledger may open/assign the action-scoped task_id; stream subscribe and
        # worker kick must use the same id (not a stale prepare-time override).
        if result.state.task_id.strip() == "":
            raise ValueError("Flow UI submit left ExecutionState.task_id empty")
        prepared.task_id = result.state.task_id
        return result.was_applied

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
        _ = await self._authorize_message_or_permissions(params, context, metadata)

        prepared = await self._prepare_a2a_params(params, metadata)
        await self._register_push_from_send_configuration(params, task_id=prepared.task_id)

        command = prepared.flow_ui_command
        if command is not None and command.kind != FlowUIIngressKind.SUBMIT:
            return await self._process_flow_ui_control(prepared)
        if command is not None and not await self._apply_flow_ui_submit(prepared):
            return await self._projected_task(prepared.task_id)

        if prepared.is_takeover_user_reply:
            _ = [event async for event in self._handle_takeover_user_reply(prepared)]
            return await self._projected_task(prepared.task_id)

        if _should_return_immediately(params):
            await self.create_task(prepared)
            return await self._projected_task(prepared.task_id)

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
        projected = await self._projected_task(prepared.task_id)
        if _a2a_projection_is_parked(projected):
            # In-process enqueue (sync_tools) finishes while collect is blocked
            # off the event loop: Pub/Sub drops, collect waits until pytest timeout.
            # Durable projection is the source of truth.
            _ = collect_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await collect_task
            return projected

        events = await collect_task
        logger.debug(f"[A2A] Collected {len(events)} events for task {prepared.task_id}")
        _ = events
        return await self._projected_task(prepared.task_id)

    @override
    async def on_message_stream(
        self, params: SendMessageRequest, context: ChannelRequestContext = None
    ) -> AsyncGenerator[Message | Task | TaskStatusUpdateEvent | TaskArtifactUpdateEvent, None]:
        set_current_channel(self)

        metadata = _message_metadata(params)
        _ = await self._authorize_message_or_permissions(params, context, metadata)

        prepared = await self._prepare_a2a_params(params, metadata)
        await self._register_push_from_send_configuration(params, task_id=prepared.task_id)

        command = prepared.flow_ui_command
        if command is not None and command.kind != FlowUIIngressKind.SUBMIT:
            yield await self._process_flow_ui_control(prepared)
            return
        if command is not None and not await self._apply_flow_ui_submit(prepared):
            yield await self._projected_task(prepared.task_id)
            return

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
        try:
            logger.info("[on_message_stream] Waiting for Redis subscription to be ready...")
            _ = await ready_event.wait()
            logger.info("[on_message_stream] Redis subscription ready, creating task...")

            await self.create_task(prepared)
            projected = await self._projected_task(prepared.task_id)
            if _a2a_projection_is_parked(projected):
                # In-process enqueue (sync_tools) finishes before the live
                # listener reads Redis: Pub/Sub is not a queue and drops.
                # Durable ledger is the source of truth — same as SendMessage.
                _ = collect_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await collect_task
                async for event in self._replay_durable_stream_events(prepared.task_id):
                    yield event
                return

            while True:
                event = await event_queue.get()
                if event is None:
                    break
                yield event
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
            task = await self.container.a2a_task_repository.get_task_for_context(
                company_id=company_id,
                flow_id=self.flow_id,
                context_id=share_context,
                task_id=params.id,
            )
            # GetTask/CancelTask id may be context_id (same contract as
            # BaseChannel._resolve_session_id_for_a2a_lookup).
            if task is None and params.id == share_context:
                shared_tasks, _ = await self.container.a2a_task_repository.list_tasks_for_context(
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
            task = await self.container.a2a_task_repository.get_task_for_owner(
                company_id=company_id,
                owner_user_id=owner_user_id,
                task_id=params.id,
            )
            if task is None:
                task = await self.container.a2a_task_repository.get_latest_for_context(
                    company_id=company_id,
                    owner_user_id=owner_user_id,
                    flow_id=self.flow_id,
                    context_id=params.id,
                )
        if task is None:
            return None
        if params.history_length and task.history:
            # protobuf repeated: truncate in place via slice copy
            kept = list(task.history)[-params.history_length :]
            del task.history[:]
            task.history.extend(kept)
        return await self._task_for_share_viewer(task, grant)

    @override
    async def on_cancel_task(
        self, params: CancelTaskRequest, context: ChannelRequestContext = None
    ) -> Task | None:
        _ = context
        logger.info(f"Cancel task: {params.id}")

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
        _ = await self.container.redis_client.set(
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
            _ = await self.container.a2a_task_projection_service.publish(
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
        *,
        after_sequence: int = 0,
    ) -> AsyncGenerator[Message | Task | TaskStatusUpdateEvent | TaskArtifactUpdateEvent, None]:
        """Snapshot Task, durable replay (afterSequence, N], then live Redis tail."""
        _ = context
        if after_sequence < 0:
            raise ValueError("after_sequence must be >= 0")
        set_current_channel(self)
        task = await self.on_get_task(GetTaskRequest(id=params.id))
        if task is None:
            return
        yield task

        grant_id = self._share_grant_id()
        if grant_id is not None:
            grant = await self._authorize_share(
                context_id=task.context_id,
                require_editor=False,
            )
            if grant is not None and grant.redacted_value_paths:
                # Raw durable/live Artifact events still carry owner-truthful
                # values. Share viewers with redaction receive only the
                # redacted snapshot Task above — never unfiltered replay/tail.
                return

        ctx = require_context()
        if ctx.active_company is None:
            raise ValueError("SubscribeToTask requires active_company")
        company_id = ctx.active_company.company_id
        stored_events = await self.container.a2a_task_repository.list_events_after_sequence(
            company_id=company_id,
            task_id=task.id,
            after_sequence=after_sequence,
        )
        latest_sequence = 0
        for stored in stored_events:
            latest_sequence = stored.sequence
            yield stored.event

        if not _task_needs_live_subscribe_tail(task):
            return

        timeout = (
            120.0 if is_testing() else float(get_flows_settings().default_flow_timeout_seconds)
        )
        subscriber = EventSubscriber(self.container.redis_client)
        live_after_sequence = latest_sequence if stored_events else after_sequence
        logger.info(
            "a2a.subscribe.live_tail",
            task_id=task.id,
            task_state=task.status.state if task.HasField("status") else None,
            after_sequence=after_sequence,
            live_after_sequence=live_after_sequence,
            replayed_events=len(stored_events),
            timeout_seconds=timeout,
        )
        async for event in subscriber.subscribe(
            task.id,
            timeout=timeout,
            after_sequence=live_after_sequence,
        ):
            yield event

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
            tasks, total = await self.container.a2a_task_repository.list_tasks_for_context(
                company_id=ctx.active_company.company_id,
                flow_id=self.flow_id,
                context_id=share_context,
                task_state=int(params.status) if params.status else None,
                limit=page_size,
                offset=offset,
            )
        else:
            tasks, total = await self.container.a2a_task_repository.list_tasks(
                company_id=ctx.active_company.company_id,
                owner_user_id=user_id,
                flow_id=self.flow_id,
                context_id=params.context_id or None,
                task_state=int(params.status) if params.status else None,
                limit=page_size,
                offset=offset,
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
            response.tasks.append(await self._task_for_share_viewer(task, share_grant))

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
        logger.info(f"Set push notification config for task: {params.task_id}")
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
        logger.info(f"Get push notification config for task: {params.task_id}")
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
        if self._share_grant_id() is not None:
            raise PermissionError("Shared sessions cannot manage push endpoints")
        await delete_push_config(params)
        logger.info(
            f"Deleted push notification config: {params.id} for task: {params.task_id}"
        )
