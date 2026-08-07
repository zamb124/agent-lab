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

from apps.flows.src.a2a.representation_service import FlowUIRepresentationService
from apps.flows.src.runtime.message_author import build_flow_message_author
from core.a2a import make_task_status
from core.a2a.codec import struct_from_mapping
from core.state import ExecutionState
from core.state.flow_ui import FlowUITransition
from core.state.interrupt import InterruptKind
from core.types import JsonArray, JsonObject, JsonValue, parse_json_object

if TYPE_CHECKING:
    from core.state import InterruptData

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
        self._flow_ui_representation: FlowUIRepresentationService = (
            FlowUIRepresentationService()
        )

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
        artifact_name: str = "response",
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

    async def emit_user_message(
        self,
        text: str,
        *,
        mutation_id: str,
        files: JsonArray | None = None,
    ) -> None:
        """Per-turn user bubble Artifact.

        `metadata.mutation_id` — идентичность submit'а: клиент строго по ней
        consume'ит optimistic pending turn (никакого текстового сравнения).
        """
        if mutation_id.strip() == "":
            raise ValueError("emit_user_message requires mutation_id")
        parts: list[Part] = []
        if text != "":
            parts.append(_text_part(text))
        if files:
            parts.append(_data_part({"files": files}))
        if not parts:
            raise ValueError("emit_user_message requires text or files")
        artifact = Artifact(
            artifact_id=self._artifact_stream_id("user_message"),
            name="user_message",
            parts=parts,
        )
        _apply_struct_metadata(artifact.metadata, {"mutation_id": mutation_id})
        event = TaskArtifactUpdateEvent(
            task_id=self.state.task_id,
            context_id=self.state.context_id,
            artifact=artifact,
            append=False,
            last_chunk=True,
        )
        await self._publish(event)
        self._closed_artifact_streams.add("user_message")

    async def emit_reasoning(self, text: str) -> None:
        """Публикует чанк reasoning (тот же контракт, что emit_text с именем артефакта reasoning)."""
        await self.emit_text(text, append=True, last_chunk=False, artifact_name="reasoning")

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

    async def emit_flow_ui_transition(self, transition: FlowUITransition) -> None:
        """Encode one accepted domain transition into exactly one negotiated representation."""
        artifacts = self._flow_ui_representation.encode_transition(
            transition,
            self.state.a2a_representation,
        )
        for artifact in artifacts:
            event = TaskArtifactUpdateEvent(
                task_id=self.state.task_id,
                context_id=self.state.context_id,
                artifact=artifact,
                append=False,
                last_chunk=False,
                metadata=struct_from_mapping(
                    {
                        "platformEventId": (
                            f"flow-ui:{transition.transition_id}:{artifact.artifact_id}"
                        )
                    }
                ),
            )
            await self._publish(event)

    async def emit_flow_ui_snapshot(self) -> None:
        """Publish the authoritative current screen for bootstrap/reconnect."""
        artifacts = self._flow_ui_representation.encode_snapshot(
            self.state.ui_document,
            self.state.a2a_representation,
        )
        for artifact in artifacts:
            event = TaskArtifactUpdateEvent(
                task_id=self.state.task_id,
                context_id=self.state.context_id,
                artifact=artifact,
                append=False,
                # Stable Flow UI artifact_id is replaced across the Task lifetime;
                # lastChunk would forbid later document revisions.
                last_chunk=False,
                metadata=struct_from_mapping(
                    {
                        "platformEventId": (
                            f"flow-ui:snapshot:{self.state.task_id}:"
                            f"{self.state.ui_document.revision}:{artifact.artifact_id}"
                        )
                    }
                ),
            )
            await self._publish(event)

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
