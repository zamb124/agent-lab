"""
Базовые абстрактные классы для стриминга событий.
"""

import uuid
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from a2a.helpers.proto_helpers import new_data_part, new_text_part
from a2a.types import (
    Artifact,
    Message,
    Part,
    Role,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatusUpdateEvent,
)
from google.protobuf.struct_pb2 import Struct

from apps.flows.src.flow_ui.projection import (
    block_paths,
    project_state,
    referenced_paths,
)
from apps.flows.src.runtime.message_author import build_flow_message_author
from apps.flows.src.state import ExecutionState
from apps.flows.src.state.interrupt import InterruptKind
from core.a2a import make_task_status
from core.a2a.codec import struct_from_mapping
from core.types import JsonObject, JsonValue, parse_json_object, require_json_object
from core.ui_document.document import FlowUIDocument, iter_blocks
from core.ui_document.json_patch import json_patch_operations
from core.ui_document.protocol import (
    CONVERSATION_SLOT_ID,
    FLOW_UI_MEDIA_TYPE,
    JSON_MEDIA_TYPE,
    JSON_PATCH_MEDIA_TYPE,
    REASONING_ARTIFACT_NAME,
    RESPONSE_ARTIFACT_NAME,
    STATE_ARTIFACT_ID,
    UI_ARTIFACT_ID,
    FlowUIEvent,
    FlowUIRender,
)

if TYPE_CHECKING:
    from apps.flows.src.state import InterruptData

StreamEvent = TaskStatusUpdateEvent | TaskArtifactUpdateEvent


def _text_part(text: str) -> Part:
    return new_text_part(text)


def _data_part(data: JsonObject) -> Part:
    return new_data_part(data)


def _apply_struct_metadata(target: Struct, metadata: JsonObject) -> None:
    """Копирует JSON object в protobuf Struct-поле `.metadata`."""
    if not metadata:
        return
    target.CopyFrom(struct_from_mapping(metadata))


class BaseEmitter(ABC):
    """
    Базовый класс для публикации событий.

    Реализации:
    - Emitter: публикация в Redis Pub/Sub
    - InMemoryEmitter: хранение в памяти (для внешних агентов)
    """

    state: ExecutionState
    _span_context: JsonObject | None

    def __init__(self, state: ExecutionState):
        self.state = state
        self._span_context = None
        self._node_run_counts: dict[str, int] = {}
        self._artifact_stream_ids: dict[str, str] = {}
        self._closed_artifact_streams: set[str] = set()
        self._state_projection: JsonObject | None = None
        self._conversation_paths: set[str] = set()
        self._ui_artifact_started: bool = False

    def next_node_run_index(self, node_id: str) -> int:
        current = self._node_run_counts.get(node_id, 0)
        self._node_run_counts[node_id] = current + 1
        return current

    def _artifact_stream_id(self, artifact_name: str) -> str:
        if artifact_name.strip() == "":
            raise ValueError("artifact_name must be non-empty")
        artifact_id = self._artifact_stream_ids.get(artifact_name)
        if artifact_id is None or artifact_name in self._closed_artifact_streams:
            artifact_id = str(uuid.uuid4())
            self._artifact_stream_ids[artifact_name] = artifact_id
            self._closed_artifact_streams.discard(artifact_name)
        return artifact_id

    def _create_message(
        self,
        text: str,
        metadata: JsonObject | None = None,
        message_id: str | None = None,
    ) -> Message:
        """Создаёт A2A Message объект."""
        message_metadata: JsonObject = dict(metadata or {})
        message_metadata["author"] = build_flow_message_author(self.state)
        message = Message(
            message_id=message_id or str(uuid.uuid4()),
            role=Role.ROLE_AGENT,
            parts=[_text_part(text)],
        )
        _apply_struct_metadata(message.metadata, message_metadata)
        return message

    async def emit_text(
        self,
        text: str,
        append: bool = True,
        last_chunk: bool = False,
        *,
        artifact_name: str = RESPONSE_ARTIFACT_NAME,
    ) -> None:
        """Публикует текстовый чанк (LLM: response; оператор: operator_reply)."""
        artifact = Artifact(
            artifact_id=self._artifact_stream_id(artifact_name),
            name=artifact_name,
            parts=[_text_part(text)],
        )
        _apply_struct_metadata(
            artifact.metadata,
            {"author": build_flow_message_author(self.state)},
        )

        event = TaskArtifactUpdateEvent(
            task_id=self.state.task_id,
            context_id=self.state.context_id,
            artifact=artifact,
            append=append,
            last_chunk=last_chunk,
        )

        await self._publish(event)
        if last_chunk:
            self._closed_artifact_streams.add(artifact_name)

    async def emit_reasoning(self, text: str) -> None:
        """Публикует чанк reasoning (тот же контракт, что emit_text с именем артефакта reasoning)."""
        await self.emit_text(text, append=True, last_chunk=False, artifact_name=REASONING_ARTIFACT_NAME)

    async def emit_tool_call(
        self,
        tool_name: str,
        tool_args: JsonObject,
        tool_call_id: str,
        react_role: str = "standard",
    ) -> None:
        """Публикует событие вызова инструмента."""
        if tool_call_id.strip() == "":
            raise ValueError("tool_call_id must be non-empty")
        stream_name = f"tool_call:{tool_call_id}"
        artifact = Artifact(
            artifact_id=self._artifact_stream_id(stream_name),
            name=stream_name,
            parts=[_data_part({
                "tool": tool_name,
                "args": tool_args,
                "tool_call_id": tool_call_id,
                "react_role": react_role,
            })],
        )

        event = TaskArtifactUpdateEvent(
            task_id=self.state.task_id,
            context_id=self.state.context_id,
            artifact=artifact,
            append=False,
            last_chunk=True,
        )

        await self._publish(event)
        self._closed_artifact_streams.add(stream_name)

    async def emit_tool_result(
        self,
        tool_name: str,
        result: JsonValue,
        tool_call_id: str,
    ) -> None:
        """Публикует результат выполнения инструмента."""
        if tool_call_id.strip() == "":
            raise ValueError("tool_call_id must be non-empty")
        stream_name = f"tool_result:{tool_call_id}"
        artifact = Artifact(
            artifact_id=self._artifact_stream_id(stream_name),
            name=stream_name,
            parts=[_data_part({
                "tool": tool_name,
                "result": result,
                "tool_call_id": tool_call_id,
            })],
        )

        event = TaskArtifactUpdateEvent(
            task_id=self.state.task_id,
            context_id=self.state.context_id,
            artifact=artifact,
            append=False,
            last_chunk=True,
        )

        await self._publish(event)
        self._closed_artifact_streams.add(stream_name)

    async def emit_complete(
        self,
        response: str,
        message_id: str | None = None,
        has_artifact: bool = False,
    ) -> None:
        """Публикует событие завершения выполнения."""
        resolved_message_id = message_id or f"status:{self.state.task_id}:completed"
        event = TaskStatusUpdateEvent(
            task_id=self.state.task_id,
            context_id=self.state.context_id,
            status=make_task_status(
                TaskState.TASK_STATE_COMPLETED,
                message=self._create_message(response, message_id=resolved_message_id),
            ),
        )
        _apply_struct_metadata(
            event.metadata,
            {
                "has_artifact": has_artifact,
                "platformEventId": f"terminal:{self.state.task_id}:completed",
            },
        )

        await self._publish(event)

    async def emit_interrupt(
        self,
        interrupt: "InterruptData",
        message_id: str | None = None,
    ) -> None:
        """Публикует input_required с полным объектом interrupt в metadata."""
        interrupt_payload = parse_json_object(interrupt.model_dump_json(), "InterruptData")
        meta: JsonObject = {"platform_interrupt": interrupt_payload}
        is_oauth = interrupt.body.kind == InterruptKind.OAUTH_REQUIRED
        is_handoff = interrupt.body.kind == InterruptKind.HANDOFF
        # operator_task: terminal-ish interrupt; oauth/handoff — live SubscribeToTask.
        if is_handoff:
            meta["platform_handoff_continue"] = True
        if is_oauth:
            meta["platform_oauth_continue"] = True
        event = TaskStatusUpdateEvent(
            task_id=self.state.task_id,
            context_id=self.state.context_id,
            status=make_task_status(
                TaskState.TASK_STATE_INPUT_REQUIRED,
                message=self._create_message(
                    interrupt.question,
                    metadata=meta,
                    message_id=message_id,
                ),
            ),
        )
        _apply_struct_metadata(event.metadata, meta)

        await self._publish(event)

    async def emit_cancelled(self) -> None:
        """Публикует событие отмены выполнения."""
        event = TaskStatusUpdateEvent(
            task_id=self.state.task_id,
            context_id=self.state.context_id,
            status=make_task_status(
                TaskState.TASK_STATE_CANCELED,
                message=self._create_message(
                    "Task cancelled",
                    message_id=f"status:{self.state.task_id}:canceled",
                ),
            ),
        )
        _apply_struct_metadata(
            event.metadata,
            {"platformEventId": f"terminal:{self.state.task_id}:canceled"},
        )
        await self._publish(event)

    async def emit_error(
        self,
        error: str,
        message_id: str | None = None,
    ) -> None:
        """Публикует событие ошибки."""
        resolved_message_id = message_id or f"status:{self.state.task_id}:failed"
        event = TaskStatusUpdateEvent(
            task_id=self.state.task_id,
            context_id=self.state.context_id,
            status=make_task_status(
                TaskState.TASK_STATE_FAILED,
                message=self._create_message(error, message_id=resolved_message_id),
            ),
        )
        _apply_struct_metadata(
            event.metadata,
            {"platformEventId": f"terminal:{self.state.task_id}:failed"},
        )

        await self._publish(event)

    async def emit(self, event: StreamEvent) -> None:
        """Публикует произвольное событие (StreamEvent от runner)."""
        await self._publish(event)

    async def emit_ping(self, *, sequence: int | None = None) -> None:
        """Публикует heartbeat кадр для живого SSE-потока без пользовательского текста."""
        now = datetime.now(timezone.utc)
        metadata: JsonObject = {
            "platform_ping": True,
            "sent_at": now.isoformat(),
        }
        if sequence is not None:
            metadata["sequence"] = sequence

        status = make_task_status(TaskState.TASK_STATE_WORKING)
        status.timestamp.FromDatetime(now)
        event = TaskStatusUpdateEvent(
            task_id=self.state.task_id,
            context_id=self.state.context_id,
            status=status,
        )
        _apply_struct_metadata(event.metadata, metadata)

        await self._publish(event)

    async def emit_node_start(
        self,
        node_id: str,
        node_type: str,
    ) -> None:
        """Публикует событие начала выполнения ноды."""
        artifact = Artifact(
            artifact_id=str(uuid.uuid4()),
            name=f"node_start_{node_id}",
            parts=[_data_part({
                "event": "node_start",
                "node_id": node_id,
                "node_type": node_type,
            })],
        )

        event = TaskArtifactUpdateEvent(
            task_id=self.state.task_id,
            context_id=self.state.context_id,
            artifact=artifact,
        )

        await self._publish(event)

    async def emit_node_complete(
        self,
        node_id: str,
        *,
        node_type: str,
        result_preview: str = "",
        duration_ms: int,
        run_index: int,
        primary_field: str = "",
        diff: list[JsonObject] | None = None,
        steps: list[JsonObject] | None = None,
    ) -> None:
        """Публикует событие завершения ноды."""
        payload: JsonObject = {
            "event": "node_complete",
            "node_id": node_id,
            "node_type": node_type,
            "result_preview": result_preview[:200],
            "duration_ms": duration_ms,
            "run_index": run_index,
        }
        if primary_field:
            payload["primary_field"] = primary_field
        if diff is not None:
            payload["diff"] = diff
        if steps is not None:
            payload["steps"] = steps
        artifact = Artifact(
            artifact_id=str(uuid.uuid4()),
            name=f"node_complete_{node_id}",
            parts=[_data_part(payload)],
        )

        event = TaskArtifactUpdateEvent(
            task_id=self.state.task_id,
            context_id=self.state.context_id,
            artifact=artifact,
        )

        await self._publish(event)

    async def emit_node_error(
        self,
        node_id: str,
        error: str,
        *,
        node_type: str,
        duration_ms: int,
        run_index: int,
    ) -> None:
        """Публикует событие ошибки в ноде."""
        artifact = Artifact(
            artifact_id=str(uuid.uuid4()),
            name=f"node_error_{node_id}",
            parts=[_data_part({
                "event": "node_error",
                "node_id": node_id,
                "node_type": node_type,
                "error": error[:500],
                "duration_ms": duration_ms,
                "run_index": run_index,
            })],
        )

        event = TaskArtifactUpdateEvent(
            task_id=self.state.task_id,
            context_id=self.state.context_id,
            artifact=artifact,
        )

        await self._publish(event)

    async def emit_edge_executed(
        self,
        edge_index: int,
        from_node: str,
        to_node: str,
    ) -> None:
        """Публикует факт прохождения ребра (для подсветки графа в UI)."""
        artifact = Artifact(
            artifact_id=str(uuid.uuid4()),
            name=f"edge_executed_{edge_index}_{from_node}_{to_node}",
            parts=[_data_part({
                "event": "edge_executed",
                "edge_index": edge_index,
                "from_node": from_node,
                "to_node": to_node,
            })],
        )

        event = TaskArtifactUpdateEvent(
            task_id=self.state.task_id,
            context_id=self.state.context_id,
            artifact=artifact,
        )

        await self._publish(event)

    async def emit_edge_error(
        self,
        edge_index: int,
        from_node: str,
        to_node: str,
        error: str,
    ) -> None:
        """Публикует ошибку вычисления условия ребра (подсветка в UI)."""
        err = error if len(error) <= 500 else error[:500]
        artifact = Artifact(
            artifact_id=str(uuid.uuid4()),
            name=f"edge_error_{edge_index}_{from_node}_{to_node}",
            parts=[_data_part({
                "event": "edge_error",
                "edge_index": edge_index,
                "from_node": from_node,
                "to_node": to_node,
                "error": err,
            })],
        )

        event = TaskArtifactUpdateEvent(
            task_id=self.state.task_id,
            context_id=self.state.context_id,
            artifact=artifact,
        )

        await self._publish(event)

    async def emit_file_artifact(
        self,
        file_ids: list[str],
        *,
        artifact_name: str = "operator_files",
    ) -> None:
        """Публикует артефакт со списком ID прикреплённых файлов."""
        artifact = Artifact(
            artifact_id=str(uuid.uuid4()),
            name=artifact_name,
            parts=[_data_part({"file_ids": file_ids})],
        )
        event = TaskArtifactUpdateEvent(
            task_id=self.state.task_id,
            context_id=self.state.context_id,
            artifact=artifact,
            append=False,
            last_chunk=True,
        )
        await self._publish(event)

    async def emit_artifact(
        self,
        data: str,
        name: str = "artifact",
    ) -> None:
        """Публикует артефакт (JSON данные)."""
        artifact = Artifact(
            artifact_id=str(uuid.uuid4()),
            name=name,
            parts=[_data_part({"content": data})],
        )

        event = TaskArtifactUpdateEvent(
            task_id=self.state.task_id,
            context_id=self.state.context_id,
            artifact=artifact,
        )

        await self._publish(event)

    async def emit_exact_artifact(
        self,
        artifact: Artifact,
        *,
        append: bool = False,
        last_chunk: bool = True,
    ) -> None:
        """Publish a fully materialised Artifact without re-synthesizing Parts."""
        if artifact.artifact_id.strip() == "":
            raise ValueError("emit_exact_artifact requires artifact.artifact_id")
        event = TaskArtifactUpdateEvent(
            task_id=self.state.task_id,
            context_id=self.state.context_id,
            artifact=artifact,
            append=append,
            last_chunk=last_chunk,
        )
        await self._publish(event)
        if last_chunk and artifact.name.strip() != "":
            self._closed_artifact_streams.add(artifact.name)

    async def emit_state(self, interface: FlowUIDocument) -> None:
        """Проекция state по путям интерфейса: первый вызов в Task — snapshot, дальше — JSON Patch."""
        paths = set(referenced_paths(interface, self.state.ui_slots)) | self._conversation_paths
        state_json = require_json_object(
            self.state.model_dump(mode="json", exclude_none=False),
            "ExecutionState",
        )
        projection = project_state(state_json, paths)
        previous = self._state_projection
        if previous is None:
            part = _data_part(projection)
            part.media_type = JSON_MEDIA_TYPE
            append = False
        else:
            operations = json_patch_operations(previous, projection)
            if not operations:
                return
            part = new_data_part([operation.model_dump(mode="json") for operation in operations])
            part.media_type = JSON_PATCH_MEDIA_TYPE
            append = True
        self._state_projection = projection
        await self._publish(
            TaskArtifactUpdateEvent(
                task_id=self.state.task_id,
                context_id=self.state.context_id,
                artifact=Artifact(artifact_id=STATE_ARTIFACT_ID, name=STATE_ARTIFACT_ID, parts=[part]),
                append=append,
                last_chunk=False,
            )
        )

    async def emit_ui_event(self, event: FlowUIEvent) -> None:
        """Render/navigate агента одним Part артефакта ``ui``; рендер в ленту расширяет проекцию state."""
        if isinstance(event, FlowUIRender) and event.slot_id == CONVERSATION_SLOT_ID:
            for block in iter_blocks(event.blocks):
                self._conversation_paths.update(block_paths(block))
        part = _data_part(event.model_dump(mode="json"))
        part.media_type = FLOW_UI_MEDIA_TYPE
        await self._publish(
            TaskArtifactUpdateEvent(
                task_id=self.state.task_id,
                context_id=self.state.context_id,
                artifact=Artifact(artifact_id=UI_ARTIFACT_ID, name=UI_ARTIFACT_ID, parts=[part]),
                append=self._ui_artifact_started,
                last_chunk=False,
            )
        )
        self._ui_artifact_started = True

    async def emit_ui_events(self, events: list[FlowUIEvent]) -> None:
        for event in events:
            await self.emit_ui_event(event)

    async def flush_ui(self, interface: FlowUIDocument) -> None:
        """Точка публикации runtime: накопленные ui-события, затем изменения state."""
        await self.emit_ui_events(self.state.drain_ui_events())
        await self.emit_state(interface)

    async def emit_breakpoint(
        self,
        node_id: str,
        node_type: str,
        state_snapshot: JsonObject,
    ) -> None:
        """
        Публикует событие срабатывания breakpoint.

        Использует TASK_STATE_INPUT_REQUIRED (ждём "Continue" от пользователя).
        Breakpoint отличается от interrupt по metadata.breakpoint=true.
        """
        event = TaskStatusUpdateEvent(
            task_id=self.state.task_id,
            context_id=self.state.context_id,
            status=make_task_status(
                TaskState.TASK_STATE_INPUT_REQUIRED,
                message=self._create_message(f"Breakpoint at node '{node_id}'"),
            ),
        )
        _apply_struct_metadata(
            event.metadata,
            {
                "breakpoint": True,
                "node_id": node_id,
                "node_type": node_type,
                "state_snapshot": state_snapshot,
            },
        )
        await self._publish(event)

    @abstractmethod
    async def _publish(self, event: StreamEvent) -> None:
        """Публикует событие. Реализуется в наследниках."""
        pass


class BaseSubscriber(ABC):
    """
    Базовый класс для подписки на события.

    Реализации:
    - RedisSubscriber: подписка на Redis Pub/Sub
    - InMemorySubscriber: чтение из памяти
    """

    @abstractmethod
    def subscribe(
        self,
        task_id: str,
        timeout: float = 300.0,
    ) -> AsyncIterator[StreamEvent]:
        """Подписывается на события задачи."""
        raise NotImplementedError

    async def collect(
        self,
        task_id: str,
        timeout: float = 300.0,
    ) -> list[StreamEvent]:
        """Собирает все события до финального."""
        events: list[StreamEvent] = []
        async for event in self.subscribe(task_id, timeout):
            events.append(event)
        return events


__all__ = ["BaseEmitter", "BaseSubscriber", "StreamEvent"]
